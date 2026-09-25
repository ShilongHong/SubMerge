import io
import tempfile
import unittest
from pathlib import Path

import yaml

import app as submerge


class V2FrozenRulesTest(unittest.TestCase):
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

    @staticmethod
    def subscription(node, group, domain, server):
        return yaml.safe_dump({
            'proxies': [{
                'name': node, 'type': 'ss', 'server': server, 'port': 443,
                'cipher': 'aes-128-gcm', 'password': 'test'
            }],
            'proxy-groups': [{'name': group, 'type': 'select', 'proxies': [node, 'DIRECT']}],
            'rules': [f'DOMAIN-SUFFIX,{domain},{group}', f'MATCH,{group}']
        }, allow_unicode=True)

    def create_config(self, second_in_rules):
        main = self.subscription('🇭🇰 A', '🚀 Main', 'a.example', '1.1.1.1')
        second = self.subscription('🇯🇵 B', 'Second', 'b.example', '2.2.2.2')
        response = self.client.post('/api/create', data={
            'sub_name_0': '主订阅', 'sub_url_0': '', 'is_main_0': 'true',
            'in_rules_0': 'true', 'enable_auto_0': 'true', 'traffic_main_0': 'false',
            'sub_file_0': (io.BytesIO(main.encode()), 'main.yaml'),
            'sub_name_1': '第二订阅', 'sub_url_1': '', 'is_main_1': 'false',
            'in_rules_1': 'true' if second_in_rules else 'false',
            'enable_auto_1': 'false', 'traffic_main_1': 'false',
            'sub_file_1': (io.BytesIO(second.encode()), 'second.yaml')
        }, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        return response.get_json()['token']

    def fetch(self, path, user_agent='clash-verge/v2.4.6'):
        response = self.client.get(path, headers={'User-Agent': user_agent})
        self.assertEqual(response.status_code, 200)
        return yaml.safe_load(response.get_data(as_text=True))

    def test_supersub_first_and_rules_frozen(self):
        token = self.create_config(second_in_rules=False)
        v1 = self.fetch(f'/api/subscribe?token={token}')
        v2 = self.fetch(f'/api/subscribe/v2?token={token}')
        template = submerge.load_v2_template()

        # 节点和其他顶层配置与 V1 一致，规则完全来自固化模板。
        self.assertEqual(v2['proxies'], v1['proxies'])
        self.assertEqual({k: v for k, v in v2.items() if k not in {'proxy-groups', 'rules'}},
                         {k: v for k, v in v1.items() if k not in {'proxy-groups', 'rules'}})
        self.assertEqual(v2['rules'], template['rules'])
        self.assertNotIn('DOMAIN-SUFFIX,a.example,🚀 Main', v2['rules'])

        groups = {group['name']: group for group in v2['proxy-groups']}
        names = [group['name'] for group in v2['proxy-groups']]
        # 本地上传的订阅没有流量信息，因此不会生成节点信息组。
        self.assertEqual(names[:4], ['SuperSub', '主订阅', '第二订阅', '主订阅_Auto'])
        # 规则组按模板顺序输出，名称统一以 emoji 开头。
        rule_groups = names[4:]
        self.assertEqual(rule_groups, [group['name'] for group in template['proxy_groups']])
        self.assertEqual(rule_groups[0], '🧲 海外AI')
        self.assertEqual(rule_groups[-1], '🚧 屏蔽访问')
        self.assertTrue(all(not name[0].isascii() for name in rule_groups))
        self.assertNotIn('BLOCK', groups)
        self.assertNotIn('下载', groups)
        self.assertNotIn('🚀 Main', groups)
        # SuperSub 先列订阅组和 Auto 组，再列全部节点（包括未参与规则的订阅），不包含流量信息节点。
        self.assertEqual(groups['SuperSub']['proxies'],
                         ['主订阅', '第二订阅', '主订阅_Auto', '[主订阅]_🇭🇰 A', '[第二订阅]_🇯🇵 B'])

        # 业务组默认 SuperSub，其余成员与 V1 的参与规则一致。
        for name in ('🐟 漏网之鱼', '🧲 海外AI', '📥 下载', '🌏 学术网站'):
            self.assertEqual(groups[name]['proxies'][0], 'SuperSub')
        # 每个规则组都有 SuperSub、DIRECT、REJECT、PASS 和参与规则的节点。
        for name in rule_groups:
            refs = groups[name]['proxies']
            for ref in ('SuperSub', 'DIRECT', 'REJECT', 'PASS', '[主订阅]_🇭🇰 A', '第二订阅'):
                self.assertIn(ref, refs, name)
            self.assertNotIn('[第二订阅]_🇯🇵 B', refs)
        self.assertEqual(groups['🎯 绕过代理']['proxies'][0], 'DIRECT')
        self.assertEqual(groups['🚧 屏蔽访问']['proxies'][0], 'REJECT')
        self.assertEqual(groups['🛑 广告过滤']['proxies'][0], '🚧 屏蔽访问')

        valid = set(groups) | {proxy['name'] for proxy in v2['proxies']} | {'DIRECT', 'REJECT', 'PASS'}
        for group in groups.values():
            self.assertTrue(set(group['proxies']) <= valid, group['name'])
        self.assertTrue(all(submerge.v2_rule_target(rule) in valid for rule in v2['rules']))
        self.assertEqual(v2['rules'][-1], 'MATCH,🐟 漏网之鱼')

    def test_in_rules_nodes_join_business_groups(self):
        token = self.create_config(second_in_rules=True)
        v2 = self.fetch(f'/api/subscribe/v2?token={token}')
        groups = {group['name']: group for group in v2['proxy-groups']}
        self.assertIn('[第二订阅]_🇯🇵 B', groups['🐟 漏网之鱼']['proxies'])

    def test_pass_only_for_mihomo_clients(self):
        token = self.create_config(second_in_rules=True)
        for user_agent, expected in (('clash-verge/v2.4.6', True), ('ClashMetaForAndroid/2.11', True),
                                     ('mihomo/1.19', True), ('ClashforWindows/0.20', False),
                                     ('Stash/2.4', False), ('Mozilla/5.0', False)):
            v2 = self.fetch(f'/api/subscribe/v2?token={token}', user_agent)
            has_pass = any('PASS' in group['proxies'] for group in v2['proxy-groups'])
            self.assertEqual(has_pass, expected, user_agent)
            self.assertTrue(all('REJECT' in group['proxies'] for group in v2['proxy-groups'][4:]))

    def test_v3_removed(self):
        token = self.create_config(second_in_rules=True)
        self.assertEqual(self.client.get(f'/api/subscribe/v3?token={token}').status_code, 404)
        self.assertEqual(self.client.get(f'/v3?token={token}').status_code, 404)

    def test_legacy_academic_rules_and_block_group_are_injected(self):
        source = yaml.safe_dump({
            'proxies': [{'name': '🇭🇰 香港 01', 'type': 'ss', 'server': '1.1.1.1'}],
            'proxy-groups': [],
            'rules': ['MATCH,DIRECT'],
        }, allow_unicode=True)
        merged, error, _ = submerge.merge_subscriptions([{
            'name': '主订阅', 'content': source, 'is_main': True,
            'in_rules': True, 'enable_auto': False,
        }])

        self.assertIsNone(error)
        groups = {group['name']: group for group in merged['proxy-groups']}
        self.assertEqual(groups['BLOCK']['type'], 'select')
        self.assertEqual(groups['BLOCK']['proxies'], ['REJECT', 'DIRECT'])
        self.assertEqual(groups['🌏 学术网站']['type'], 'select')
        academic_rules = [rule for rule in merged['rules'] if rule.endswith(',🌏 学术网站')]
        self.assertEqual(len(academic_rules), 229)
        self.assertIn('DOMAIN-SUFFIX,arxiv.org,🌏 学术网站', academic_rules)
        self.assertIn('DOMAIN-SUFFIX,scholar.google.com,🌏 学术网站', academic_rules)
        self.assertNotIn('DOMAIN-SUFFIX,scholar.google.com,挑剔的网站', merged['rules'])


if __name__ == '__main__':
    unittest.main()
