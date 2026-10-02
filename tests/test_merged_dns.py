import io
import tempfile
import unittest
from pathlib import Path

import yaml

import app as submerge


def proxy(name, server):
    return {'name': name, 'type': 'ss', 'server': server, 'port': 443,
            'cipher': 'aes-128-gcm', 'password': 'test'}


def subscription(nodes, extra=None):
    data = {
        'proxies': nodes,
        'proxy-groups': [{'name': 'Main', 'type': 'select',
                          'proxies': [node['name'] for node in nodes] + ['DIRECT']}],
        'rules': ['MATCH,Main'],
    }
    data.update(extra or {})
    return yaml.safe_dump(data, allow_unicode=True)


# 模拟 TAG：用 hosts 把节点域名指向中转入口，节点域名经 Clash 自己的 DNS 解析
MAIN_EXTRA = {
    'dns': {
        'enable': True,
        'listen': '0.0.0.0:7874',
        'enhanced-mode': 'fake-ip',
        'use-hosts': False,
        'proxy-server-nameserver': ['udp://127.0.0.1:7874'],
        'nameserver': ['https://223.5.5.5/dns-query'],
        'nameserver-policy': {'geosite:private': ['223.5.5.5']},
        'nameserver-policy:"+.private-a.com,+.private-b.com"': ['https://doh.example/dns-query#DIRECT'],
        'fake-ip-filter': ['*.lan', '+.relay.top'],
    },
    'hosts': {'n1.main-node.org': 'x1.relay.top'},
}


class MergedDnsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.original_dirs = (submerge.CONFIGS_DIR, submerge.FILES_DIR, submerge.CACHE_DIR)
        submerge.CONFIGS_DIR = str(root / 'configs')
        submerge.FILES_DIR = str(root / 'files')
        submerge.CACHE_DIR = str(root / 'cache')
        for directory in (submerge.CONFIGS_DIR, submerge.FILES_DIR, submerge.CACHE_DIR):
            Path(directory).mkdir()
        self.client = submerge.app.test_client()

    def tearDown(self):
        submerge.CONFIGS_DIR, submerge.FILES_DIR, submerge.CACHE_DIR = self.original_dirs
        self.temp_dir.cleanup()

    def create_config(self, main_text, second_text):
        response = self.client.post('/api/create', data={
            'sub_name_0': '主订阅', 'sub_url_0': '', 'is_main_0': 'true',
            'in_rules_0': 'true', 'enable_auto_0': 'false', 'traffic_main_0': 'false',
            'sub_file_0': (io.BytesIO(main_text.encode()), 'main.yaml'),
            'sub_name_1': '第二订阅', 'sub_url_1': '', 'is_main_1': 'false',
            'in_rules_1': 'true', 'enable_auto_1': 'false', 'traffic_main_1': 'false',
            'sub_file_1': (io.BytesIO(second_text.encode()), 'second.yaml'),
        }, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        return response.get_json()['token']

    def fetch(self, path):
        response = self.client.get(path, headers={'User-Agent': 'clash-verge/v2.4.6'})
        self.assertEqual(response.status_code, 200)
        return yaml.safe_load(response.get_data(as_text=True))

    def test_main_dns_kept_and_all_node_domains_skip_fake_ip(self):
        main = subscription([proxy('A', 'n1.main-node.org')], MAIN_EXTRA)
        second = subscription(
            [proxy('B', 'b.other-node.com'), proxy('C', '2.2.2.2'), proxy('D', '2001:db8::1')],
            {'hosts': {'b.other-node.com': '9.9.9.9', 'www.google.com': '6.6.6.6'},
             'dns': {'nameserver': ['8.8.8.8']}})
        token = self.create_config(main, second)

        for path in (f'/api/subscribe?token={token}', f'/api/subscribe/v2?token={token}'):
            config = self.fetch(path)
            dns = config['dns']
            # 主订阅的 DNS 原样保留，不被其他订阅覆盖
            self.assertEqual(dns['listen'], '0.0.0.0:7874')
            self.assertEqual(dns['proxy-server-nameserver'], ['udp://127.0.0.1:7874'])
            self.assertEqual(dns['nameserver'], ['https://223.5.5.5/dns-query'])
            # 所有订阅的节点域名都加入 fake-ip-filter，IP 节点跳过
            self.assertEqual(dns['fake-ip-filter'],
                             ['*.lan', '+.relay.top', 'n1.main-node.org', 'b.other-node.com'])
            # 有 hosts 时强制启用
            self.assertTrue(dns['use-hosts'])
            # 写坏的 nameserver-policy 键被修正
            self.assertFalse([key for key in dns if key.startswith('nameserver-policy:')])
            self.assertEqual(dns['nameserver-policy'], {
                'geosite:private': ['223.5.5.5'],
                '+.private-a.com,+.private-b.com': ['https://doh.example/dns-query#DIRECT'],
            })
            # 主订阅 hosts 全保留；其他订阅只取自己节点域名的条目
            self.assertEqual(config['hosts'], {
                'n1.main-node.org': 'x1.relay.top',
                'b.other-node.com': '9.9.9.9',
            })

    def test_default_dns_when_main_has_none(self):
        token = self.create_config(subscription([proxy('A', 'a.node.org')]),
                                   subscription([proxy('B', 'b.node.org')]))
        config = self.fetch(f'/api/subscribe?token={token}')
        dns = config['dns']
        self.assertEqual(dns['proxy-server-nameserver'], submerge.DEFAULT_DNS['proxy-server-nameserver'])
        self.assertEqual(dns['fake-ip-filter'][-2:], ['a.node.org', 'b.node.org'])
        self.assertNotIn('hosts', config)
        # 默认配置本身不被修改
        self.assertNotIn('a.node.org', submerge.DEFAULT_DNS['fake-ip-filter'])

    def test_whitelist_filter_mode_untouched(self):
        dns = submerge.build_merged_dns(
            {'enhanced-mode': 'fake-ip', 'fake-ip-filter-mode': 'whitelist', 'fake-ip-filter': ['+.x.com']},
            [proxy('A', 'a.node.org')])
        self.assertEqual(dns['fake-ip-filter'], ['+.x.com'])


if __name__ == '__main__':
    unittest.main()
