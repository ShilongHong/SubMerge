// SubMerge 配置页逻辑：原生 DOM，无依赖
(function () {
    'use strict';

    // 与后端注入的分组、V2 SuperSub 及内置策略同名会冲突
    var RESERVED_NAMES = ['节点信息', '下载', '挑剔的网站', 'TikTok解锁', '屏蔽视频广告', '常见广告域名',
        'BLOCK', '🌏 学术网站', 'SuperSub', 'DIRECT', 'REJECT', 'PASS', 'GLOBAL'];
    var RECENT_KEY = 'submerge-recent';
    var THEME_KEY = 'submerge-theme';

    var state = {
        token: null,       // 当前编辑的 Token；null 表示新建
        snapshot: null,    // 最近一次保存/载入时的表单快照，用于判断未保存修改
        nextId: 1,
        busy: false
    };

    var $ = function (sel, root) { return (root || document).querySelector(sel); };
    var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

    var el = {
        form: $('#mergeForm'),
        subList: $('#subList'),
        template: $('#subTemplate'),
        mainSelect: $('#mainSelect'),
        trafficSelect: $('#trafficSelect'),
        submitBtn: $('#submitBtn'),
        actionStatus: $('#actionStatus'),
        intro: $('#intro'),
        editBanner: $('#editBanner'),
        editToken: $('#editToken'),
        resultPanel: $('#resultPanel'),
        resultIntro: $('#resultIntro'),
        tokenBox: $('#tokenBox'),
        tokenValue: $('#tokenValue'),
        checkBox: $('#checkBox'),
        checkList: $('#checkList'),
        dialog: $('#loadDialog'),
        tokenInput: $('#tokenInput'),
        tokenError: $('#tokenError'),
        loadSubmit: $('#loadSubmit'),
        recentBox: $('#recentBox'),
        recentList: $('#recentList'),
        toasts: $('#toasts')
    };

    // ---------- 通用 ----------

    function toast(message, type) {
        var node = document.createElement('div');
        node.className = 'toast' + (type === 'error' ? ' toast-error' : '');
        node.textContent = message;
        el.toasts.appendChild(node);
        setTimeout(function () {
            node.classList.add('is-leaving');
            setTimeout(function () { node.remove(); }, 250);
        }, type === 'error' ? 5000 : 2600);
    }

    function setBusy(button, busy, label) {
        button.disabled = busy;
        button.classList.toggle('is-busy', busy);
        if (label) $('.btn-label', button).textContent = label;
    }

    function copyText(text, what) {
        var done = function () { toast((what || '内容') + '已复制'); };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text) && done(); });
        } else if (fallbackCopy(text)) {
            done();
        } else {
            toast('复制失败，请手动选中复制', 'error');
        }
    }

    function fallbackCopy(text) {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        area.remove();
        return ok;
    }

    function apiUrl(path) {
        return new URL(path, document.baseURI).href;
    }

    function subscribeUrls(token) {
        var t = encodeURIComponent(token);
        return {
            v1: apiUrl('api/subscribe?token=' + t),
            v2: apiUrl('api/subscribe/v2?token=' + t)
        };
    }

    function shortToken(token) {
        return token.length > 12 ? token.slice(0, 6) + '…' + token.slice(-4) : token;
    }

    function readJson(response) {
        return response.json().catch(function () {
            throw new Error('服务器返回了无法识别的内容（HTTP ' + response.status + '）');
        });
    }

    // ---------- 订阅卡片 ----------

    function cards() { return $$('.sub-card', el.subList); }

    function addSub(data, options) {
        data = data || {};
        var id = state.nextId++;
        var card = el.template.content.firstElementChild.cloneNode(true);
        card.dataset.id = String(id);
        if (!(options && options.silent)) card.classList.add('is-new');

        var nameInput = $('.sub-name', card);
        nameInput.id = 'sub-' + id + '-name';
        $('[data-for="name"]', card).setAttribute('for', nameInput.id);
        nameInput.value = data.name || defaultName();

        var sourceLabel = $('[data-label="source"]', card);
        sourceLabel.id = 'sub-' + id + '-source';
        $('.seg', card).setAttribute('aria-labelledby', sourceLabel.id);
        $$('.seg input', card).forEach(function (radio) { radio.name = 'source-' + id; });

        var urlInput = $('.sub-url', card);
        urlInput.setAttribute('aria-label', '订阅链接');
        urlInput.value = data.url || '';

        $('.in-rules', card).checked = data.in_rules !== false;
        $('.enable-auto', card).checked = !!data.enable_auto;

        if (data.file_md5 && !data.url) {
            card.dataset.fileMd5 = data.file_md5;
            setSource(card, 'file');
            showFileState(card, '已上传的文件', '重新选择文件可替换');
        }

        wireCard(card);
        el.subList.appendChild(card);
        refreshCards();
        return card;
    }

    function defaultName() {
        var used = cards().map(function (c) { return $('.sub-name', c).value.trim(); });
        for (var i = cards().length + 1; ; i++) {
            if (used.indexOf('订阅' + i) === -1) return '订阅' + i;
        }
    }

    function wireCard(card) {
        $('.sub-name', card).addEventListener('input', function () {
            clearError(card, 'name');
            refreshCards();
        });
        $('.sub-url', card).addEventListener('input', function () { clearError(card, 'source'); });
        $('.sub-url', card).addEventListener('blur', function () {
            // 粘贴时常带首尾空白
            this.value = this.value.trim();
        });
        $$('.seg input', card).forEach(function (radio) {
            radio.addEventListener('change', function () { setSource(card, radio.value); onFormChange(); });
        });
        $('.sub-remove', card).addEventListener('click', function () { removeSub(card); });

        var fileInput = $('.sub-file', card);
        var drop = $('.drop', card);
        fileInput.addEventListener('change', function () {
            clearError(card, 'source');
            if (fileInput.files.length) {
                var file = fileInput.files[0];
                showFileState(card, file.name, formatSize(file.size) + ' · 点击可重新选择');
            }
            onFormChange();
        });
        drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('is-over'); });
        drop.addEventListener('dragleave', function () { drop.classList.remove('is-over'); });
        drop.addEventListener('drop', function (e) {
            e.preventDefault();
            drop.classList.remove('is-over');
            if (e.dataTransfer && e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                fileInput.dispatchEvent(new Event('change'));
            }
        });
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    }

    function showFileState(card, title, hint) {
        var drop = $('.drop', card);
        drop.classList.add('has-file');
        drop.classList.remove('is-invalid');
        $('.drop-text', card).textContent = title;
        $('.drop-hint', card).textContent = hint;
    }

    function setSource(card, source) {
        $$('.seg input', card).forEach(function (radio) { radio.checked = radio.value === source; });
        $('.source-url', card).hidden = source !== 'url';
        $('.source-file', card).hidden = source !== 'file';
        clearError(card, 'source');
    }

    function sourceOf(card) {
        var checked = $('.seg input:checked', card);
        return checked ? checked.value : 'url';
    }

    function removeSub(card) {
        if (cards().length <= 1) return;
        var name = $('.sub-name', card).value.trim() || '该订阅';
        var hasContent = $('.sub-url', card).value.trim() || card.dataset.fileMd5 || $('.sub-file', card).files.length;
        if (hasContent && !window.confirm('删除「' + name + '」？保存后才会生效。')) return;
        var next = card.nextElementSibling || card.previousElementSibling;
        card.remove();
        refreshCards();
        onFormChange();
        if (next) $('.sub-name', next).focus();
    }

    // 刷新序号、标题、删除按钮、下拉选项和徽标
    function refreshCards() {
        var list = cards();
        list.forEach(function (card, index) {
            var name = $('.sub-name', card).value.trim();
            $('.sub-index', card).textContent = String(index + 1);
            var title = $('.sub-title', card);
            title.textContent = name || '未命名订阅';
            title.classList.toggle('is-placeholder', !name);
            $('.auto-name', card).textContent = (name || '名称') + '_Auto';
            var remove = $('.sub-remove', card);
            remove.disabled = list.length <= 1;
            remove.setAttribute('aria-label', '删除订阅 ' + (name || index + 1));
            remove.title = list.length <= 1 ? '至少保留一个订阅' : '删除此订阅';
        });
        refreshSelects();
    }

    function refreshSelects() {
        var list = cards();
        var mainValue = el.mainSelect.value;
        var trafficValue = el.trafficSelect.value;
        var ids = list.map(function (c) { return c.dataset.id; });

        el.mainSelect.innerHTML = '';
        el.trafficSelect.innerHTML = '';
        var follow = new Option('跟随分流规则来源', '');
        el.trafficSelect.appendChild(follow);
        list.forEach(function (card, index) {
            var label = (index + 1) + '. ' + ($('.sub-name', card).value.trim() || '未命名订阅');
            el.mainSelect.appendChild(new Option(label, card.dataset.id));
            el.trafficSelect.appendChild(new Option(label, card.dataset.id));
        });
        el.mainSelect.value = ids.indexOf(mainValue) !== -1 ? mainValue : (ids[0] || '');
        el.trafficSelect.value = ids.indexOf(trafficValue) !== -1 ? trafficValue : '';
        refreshBadges();
    }

    function refreshBadges() {
        var mainId = el.mainSelect.value;
        var trafficId = el.trafficSelect.value || mainId;
        cards().forEach(function (card) {
            var box = $('.badges', card);
            box.innerHTML = '';
            if (card.dataset.id === mainId) box.appendChild(badge('分流规则来源', ''));
            if (card.dataset.id === trafficId) box.appendChild(badge('流量信息', 'badge-traffic'));
        });
    }

    function badge(text, extra) {
        var span = document.createElement('span');
        span.className = 'badge ' + extra;
        span.textContent = text;
        return span;
    }

    // ---------- 校验与收集 ----------

    function showError(card, field, message) {
        var host = field === 'name' ? $('.field-name', card) : $('.field-source', card);
        var box = $('.field-error', host);
        box.textContent = message;
        box.hidden = false;
        box.id = 'sub-' + card.dataset.id + '-' + field + '-error';
        var input = field === 'name' ? $('.sub-name', card)
            : (sourceOf(card) === 'url' ? $('.sub-url', card) : $('.sub-file', card));
        input.setAttribute('aria-invalid', 'true');
        input.setAttribute('aria-describedby', box.id);
        if (field === 'source' && sourceOf(card) === 'file') $('.drop', card).classList.add('is-invalid');
        return input;
    }

    function clearError(card, field) {
        var host = field === 'name' ? $('.field-name', card) : $('.field-source', card);
        $('.field-error', host).hidden = true;
        $$('[aria-invalid]', host).forEach(function (input) {
            input.removeAttribute('aria-invalid');
            input.removeAttribute('aria-describedby');
        });
        $('.drop', card).classList.remove('is-invalid');
    }

    function validate() {
        var firstInvalid = null;
        var seen = {};
        cards().forEach(function (card) {
            clearError(card, 'name');
            clearError(card, 'source');
            var name = $('.sub-name', card).value.trim();
            var nameError = '';
            if (!name) nameError = '请填写名称';
            else if (name.indexOf(',') !== -1 || name.indexOf('，') !== -1) nameError = '名称不能包含逗号，否则会破坏分流规则';
            else if (RESERVED_NAMES.indexOf(name) !== -1) nameError = '「' + name + '」是内置分组名，请换一个';
            else if (/_Auto$/.test(name)) nameError = '名称不能以 _Auto 结尾，它留给自动测速组';
            else if (seen[name]) nameError = '和第 ' + seen[name] + ' 个订阅重名，请换一个';
            if (name && !seen[name]) seen[name] = cards().indexOf(card) + 1;
            if (nameError) {
                var input = showError(card, 'name', nameError);
                firstInvalid = firstInvalid || input;
            }

            var sourceError = '';
            if (sourceOf(card) === 'url') {
                var url = $('.sub-url', card).value.trim();
                if (!url) sourceError = '请粘贴订阅链接';
                else if (!/^https?:\/\/\S+$/i.test(url)) sourceError = '订阅链接应以 http:// 或 https:// 开头';
            } else if (!$('.sub-file', card).files.length && !card.dataset.fileMd5) {
                sourceError = '请选择要上传的订阅文件';
            }
            if (sourceError) {
                var target = showError(card, 'source', sourceError);
                firstInvalid = firstInvalid || target;
            }
        });
        return firstInvalid;
    }

    function collect() {
        var mainId = el.mainSelect.value;
        var trafficId = el.trafficSelect.value;
        return cards().map(function (card) {
            var isFile = sourceOf(card) === 'file';
            var fileInput = $('.sub-file', card);
            return {
                name: $('.sub-name', card).value.trim(),
                url: isFile ? '' : $('.sub-url', card).value.trim(),
                file: isFile && fileInput.files.length ? fileInput.files[0] : null,
                file_md5: isFile ? (card.dataset.fileMd5 || '') : '',
                is_main: card.dataset.id === mainId,
                in_rules: $('.in-rules', card).checked,
                enable_auto: $('.enable-auto', card).checked,
                traffic_main: card.dataset.id === trafficId
            };
        });
    }

    function snapshot() {
        var ids = cards().map(function (c) { return c.dataset.id; });
        return JSON.stringify({
            subs: collect().map(function (s) {
                return [s.name, s.url, s.file_md5, s.file ? s.file.name + ':' + s.file.size : '', s.in_rules, s.enable_auto];
            }),
            main: ids.indexOf(el.mainSelect.value),
            traffic: ids.indexOf(el.trafficSelect.value)
        });
    }

    function isDirty() { return state.snapshot !== null && snapshot() !== state.snapshot; }

    function onFormChange() {
        refreshBadges();
        updateStatus();
    }

    function updateStatus() {
        var dirty = isDirty();
        el.actionStatus.classList.toggle('is-dirty', dirty && !!state.token);
        if (!state.token) {
            el.actionStatus.textContent = '';
        } else if (dirty) {
            el.actionStatus.textContent = '有未保存的修改';
        } else {
            el.actionStatus.textContent = '所有修改已保存';
        }
    }

    // ---------- 保存 ----------

    function submit(event) {
        event.preventDefault();
        if (state.busy) return;
        var invalid = validate();
        if (invalid) {
            invalid.focus();
            if (invalid.scrollIntoView) invalid.scrollIntoView({ block: 'center', behavior: 'smooth' });
            toast('还有内容需要修改，请查看标红的地方', 'error');
            return;
        }

        var subs = collect();
        var formData = new FormData();
        if (state.token) formData.append('token', state.token);
        subs.forEach(function (sub, i) {
            formData.append('sub_name_' + i, sub.name);
            formData.append('sub_url_' + i, sub.url);
            formData.append('is_main_' + i, sub.is_main);
            formData.append('in_rules_' + i, sub.in_rules);
            formData.append('enable_auto_' + i, sub.enable_auto);
            formData.append('traffic_main_' + i, sub.traffic_main);
            formData.append('file_md5_' + i, sub.file_md5);
            if (sub.file) formData.append('sub_file_' + i, sub.file);
        });

        var wasEditing = !!state.token;
        state.busy = true;
        setBusy(el.submitBtn, true, '保存中…');

        fetch(apiUrl('api/create'), { method: 'POST', body: formData })
            .then(readJson)
            .then(function (data) {
                if (!data.success) throw new Error(data.error || '保存失败');
                return fetch(apiUrl('api/config/' + encodeURIComponent(data.token)))
                    .then(readJson)
                    .then(function (saved) {
                        // 用服务器保存的结果回填，拿到新上传文件的 MD5
                        if (saved.success) fillForm(saved.config.subscriptions || []);
                        enterEditMode(data.token);
                        rememberToken(data.token);
                        showResult(data.token, true);
                        toast(wasEditing ? '已保存，客户端更新订阅即可生效' : '订阅链接已生成');
                    });
            })
            .catch(function (error) {
                toast(error.message || '网络错误，请稍后重试', 'error');
                el.actionStatus.textContent = '保存失败：' + (error.message || '网络错误');
                el.actionStatus.classList.add('is-dirty');
            })
            .then(function () {
                state.busy = false;
                setBusy(el.submitBtn, false, state.token ? '保存修改' : '保存并生成链接');
            });
    }

    // ---------- 载入 ----------

    function fillForm(subscriptions) {
        el.subList.innerHTML = '';
        var mainCard = null;
        var trafficCard = null;
        subscriptions.forEach(function (sub) {
            var card = addSub(sub, { silent: true });
            if (sub.is_main && !mainCard) mainCard = card;
            if (sub.is_traffic_main && !trafficCard) trafficCard = card;
        });
        if (!cards().length) addSub(null, { silent: true });
        el.mainSelect.value = mainCard ? mainCard.dataset.id : cards()[0].dataset.id;
        el.trafficSelect.value = trafficCard ? trafficCard.dataset.id : '';
        refreshBadges();
    }

    function loadToken(token) {
        return fetch(apiUrl('api/config/' + encodeURIComponent(token)))
            .then(function (response) {
                if (response.status === 404) throw new Error('找不到这个 Token 对应的配置，请检查是否完整');
                return readJson(response);
            })
            .then(function (data) {
                if (!data.success) throw new Error(data.error || '载入失败');
                fillForm((data.config && data.config.subscriptions) || []);
                enterEditMode(token);
                rememberToken(token);
                showResult(token, false);
            });
    }

    function enterEditMode(token) {
        state.token = token;
        state.snapshot = snapshot();
        el.intro.hidden = true;
        el.editBanner.hidden = false;
        el.editToken.textContent = shortToken(token);
        el.editToken.title = token;
        $('.btn-label', el.submitBtn).textContent = '保存修改';
        updateStatus();
    }

    function startNew() {
        if (isDirty() && !window.confirm('当前有未保存的修改，确定放弃并新建？')) return;
        state.token = null;
        state.snapshot = null;
        el.subList.innerHTML = '';
        addSub(null, { silent: true });
        el.intro.hidden = false;
        el.editBanner.hidden = true;
        $('.btn-label', el.submitBtn).textContent = '保存并生成链接';
        hideResult();
        updateStatus();
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
        window.scrollTo({ top: 0 });
        $('.sub-name', cards()[0]).focus();
    }

    function parseTokenInput(value) {
        value = value.trim();
        var match = value.match(/[?&]token=([^&#\s]+)/);
        if (match) value = decodeURIComponent(match[1]);
        return value;
    }

    // ---------- 结果与检测 ----------

    function showResult(token, focus) {
        var urls = subscribeUrls(token);
        $$('.link-item', el.resultPanel).forEach(function (item) {
            var kind = item.dataset.kind;
            var url = urls[kind];
            $('.link-actions', item).hidden = false;
            $('.link-url', item).value = url;
            $('[data-copy]', item).onclick = function () { copyText(url, kind.toUpperCase() + ' 链接'); };
            $('[data-import]', item).href = 'clash://install-config?url=' + encodeURIComponent(url) +
                '&name=' + encodeURIComponent(kind === 'v2' ? 'SubMerge V2' : 'SubMerge');
        });
        el.resultIntro.textContent = '复制任一链接，添加到 Clash 客户端的订阅里。两个链接节点相同，可以都导入对比。';
        el.tokenBox.hidden = false;
        el.tokenValue.textContent = token;
        el.resultPanel.classList.add('is-ready');
        runCheck(false);
        if (focus) {
            el.resultPanel.focus({ preventScroll: true });
            el.resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    function hideResult() {
        $$('.link-actions', el.resultPanel).forEach(function (node) { node.hidden = true; });
        el.resultIntro.textContent = '保存后会在这里生成两个链接，节点完全相同，区别只在分流规则。';
        el.tokenBox.hidden = true;
        el.checkBox.hidden = true;
        el.resultPanel.classList.remove('is-ready');
    }

    var checkSeq = 0;

    function runCheck(refresh) {
        var token = state.token;
        if (!token) return;
        var seq = ++checkSeq;
        var names = collect().map(function (s) { return s.name; });
        el.checkBox.hidden = false;
        el.checkList.innerHTML = '';
        names.forEach(function (name) {
            el.checkList.appendChild(checkItem({ name: name }, 'pending', refresh ? '正在重新下载…' : '检测中…'));
        });
        var button = $('#recheck');
        setBusy(button, true);

        fetch(apiUrl('api/check/' + encodeURIComponent(token) + (refresh ? '?refresh=1' : '')))
            .then(readJson)
            .then(function (data) {
                if (seq !== checkSeq) return;
                if (!data.success) throw new Error(data.error || '检测失败');
                renderCheck(data);
            })
            .catch(function (error) {
                if (seq !== checkSeq) return;
                el.checkList.innerHTML = '';
                el.checkList.appendChild(note('检测失败：' + (error.message || '网络错误')));
            })
            .then(function () { if (seq === checkSeq) setBusy(button, false); });
    }

    function renderCheck(data) {
        el.checkList.innerHTML = '';
        var failed = 0;
        var total = 0;
        var mainFailed = false;
        data.subscriptions.forEach(function (sub) {
            var meta;
            var status = sub.ok ? 'ok' : 'fail';
            if (sub.ok) {
                total += sub.nodes;
                if (!sub.nodes) status = 'fail';
                meta = sub.nodes ? (sub.traffic || (sub.source === 'file' ? '本地文件，无流量信息' : '订阅未提供流量信息'))
                    : '没有解析到任何节点';
            } else {
                failed++;
                if (sub.name === data.main) mainFailed = true;
                meta = sub.error || '获取失败';
            }
            if (sub.name === data.main) meta = '分流规则来源 · ' + meta;
            el.checkList.appendChild(checkItem(sub, status, meta));
        });
        if (mainFailed) {
            el.checkList.appendChild(note('分流规则来源「' + data.main + '」获取失败，订阅链接暂时无法使用。请检查它的链接，或把分流规则来源换成其他订阅。'));
        } else if (failed) {
            el.checkList.appendChild(note('失败的订阅会被跳过，其余 ' + total + ' 个节点照常可用。'));
        }
    }

    function checkItem(sub, status, meta) {
        var li = document.createElement('li');
        li.className = 'check-item is-' + status;
        var dot = document.createElement('span');
        dot.className = 'check-dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = status === 'ok' ? '✓' : status === 'fail' ? '!' : '';
        var name = document.createElement('span');
        name.className = 'check-name';
        name.textContent = sub.name;
        var count = document.createElement('span');
        count.className = 'check-count';
        count.textContent = status === 'pending' ? '' : (sub.ok ? sub.nodes + ' 个节点' : '失败');
        var metaNode = document.createElement('span');
        metaNode.className = 'check-meta';
        metaNode.textContent = meta;
        li.append(dot, name, count, metaNode);
        return li;
    }

    function note(text) {
        var li = document.createElement('li');
        li.className = 'check-note';
        li.textContent = text;
        return li;
    }

    // ---------- 最近使用 ----------

    function readRecent() {
        try {
            var list = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
            return Array.isArray(list) ? list : [];
        } catch (e) { return []; }
    }

    function writeRecent(list) {
        try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6))); } catch (e) { /* 隐私模式等 */ }
    }

    function rememberToken(token) {
        var label = collect().map(function (s) { return s.name; }).join('、');
        var list = readRecent().filter(function (item) { return item.token !== token; });
        list.unshift({ token: token, label: label, at: Date.now() });
        writeRecent(list);
    }

    function renderRecent() {
        var list = readRecent();
        el.recentBox.hidden = !list.length;
        el.recentList.innerHTML = '';
        list.forEach(function (item) {
            var li = document.createElement('li');
            var open = document.createElement('button');
            open.type = 'button';
            open.className = 'recent-open';
            var title = document.createElement('strong');
            title.textContent = item.label || '未命名配置';
            var sub = document.createElement('span');
            sub.textContent = shortToken(item.token);
            open.append(title, sub);
            open.addEventListener('click', function () {
                el.tokenInput.value = item.token;
                el.loadSubmit.click();
            });
            var remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'icon-btn';
            remove.setAttribute('aria-label', '从最近使用中移除 ' + (item.label || shortToken(item.token)));
            remove.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
            remove.addEventListener('click', function () {
                writeRecent(readRecent().filter(function (r) { return r.token !== item.token; }));
                renderRecent();
            });
            li.append(open, remove);
            el.recentList.appendChild(li);
        });
    }

    // ---------- 对话框 ----------

    function openLoadDialog() {
        el.tokenError.hidden = true;
        el.tokenInput.removeAttribute('aria-invalid');
        el.tokenInput.value = '';
        renderRecent();
        if (el.dialog.showModal) el.dialog.showModal();
        else el.dialog.setAttribute('open', '');
        el.tokenInput.focus();
    }

    function closeLoadDialog() {
        if (el.dialog.close) el.dialog.close();
        else el.dialog.removeAttribute('open');
    }

    function submitLoad(event) {
        event.preventDefault();
        var token = parseTokenInput(el.tokenInput.value);
        var fail = function (message) {
            el.tokenError.textContent = message;
            el.tokenError.hidden = false;
            el.tokenInput.setAttribute('aria-invalid', 'true');
            el.tokenInput.focus();
        };
        if (!token) return fail('请输入 Token');
        if (!/^[A-Za-z0-9_-]{8,64}$/.test(token)) return fail('Token 格式不对，应为一串字母和数字');
        if (isDirty() && token !== state.token && !window.confirm('当前有未保存的修改，确定放弃并载入其他配置？')) return;

        setBusy(el.loadSubmit, true, '载入中…');
        loadToken(token)
            .then(function () {
                closeLoadDialog();
                toast('已载入配置');
            })
            .catch(function (error) { fail(error.message || '网络错误，请稍后重试'); })
            .then(function () { setBusy(el.loadSubmit, false, '载入配置'); });
    }

    // ---------- 主题 ----------

    function currentTheme() {
        var attr = document.documentElement.getAttribute('data-theme');
        if (attr) return attr;
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function toggleTheme() {
        var next = currentTheme() === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* 忽略 */ }
        updateThemeLabel();
    }

    function updateThemeLabel() {
        $('#themeToggle').setAttribute('aria-label', currentTheme() === 'dark' ? '切换浅色模式' : '切换深色模式');
    }

    // ---------- 初始化 ----------

    function init() {
        el.form.addEventListener('submit', submit);
        el.form.addEventListener('input', updateStatus);
        el.form.addEventListener('change', onFormChange);
        $('#addSub').addEventListener('click', function () {
            var card = addSub();
            onFormChange();
            var name = $('.sub-name', card);
            name.focus();
            name.select();
        });
        $('#openLoad').addEventListener('click', openLoadDialog);
        $('#startNew').addEventListener('click', startNew);
        $('#themeToggle').addEventListener('click', toggleTheme);
        $('#copyToken').addEventListener('click', function () { copyText(state.token, 'Token'); });
        $('#copyEditLink').addEventListener('click', function () {
            copyText(apiUrl('?token=' + encodeURIComponent(state.token)), '修改页链接');
        });
        $('#recheck').addEventListener('click', function () { runCheck(true); });
        $('#loadForm').addEventListener('submit', submitLoad);
        el.tokenInput.addEventListener('input', function () {
            el.tokenError.hidden = true;
            el.tokenInput.removeAttribute('aria-invalid');
        });
        $$('[data-close]', el.dialog).forEach(function (button) { button.addEventListener('click', closeLoadDialog); });
        el.dialog.addEventListener('click', function (e) { if (e.target === el.dialog) closeLoadDialog(); });
        window.addEventListener('beforeunload', function (e) {
            if (isDirty()) { e.preventDefault(); e.returnValue = ''; }
        });
        updateThemeLabel();

        addSub(null, { silent: true });

        var token = new URLSearchParams(window.location.search).get('token');
        if (token) {
            loadToken(token).catch(function (error) {
                toast(error.message || '载入失败', 'error');
            });
        }
    }

    init();
})();
