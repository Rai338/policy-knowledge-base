/* ============================================================
   工作台（登录后的首屏）
   视觉与交互对齐 policy-workbench 原型：
     · 空态：等宽小标 + 衬线大标题 + 居中悬浮提问卡
     · 问答态：问题（衬线）→ 答案卡 → 证据列表（编号 / 出处 / 时效 / 摘录）→ 底部吸底提问卡
   数据链路不变：/qa/ask 检索 + 原文依据 + 溯源跳转。
   ============================================================ */
(function (global) {
  'use strict';

  var ICONS = {
    paperclip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11.5l-7.4 7.4a4.2 4.2 0 0 1-6-6l7.6-7.6a2.9 2.9 0 0 1 4.1 4.1l-7.6 7.6a1.6 1.6 0 0 1-2.2-2.2l7-7"/></svg>',
    globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.4 3.4 8.5S14.3 18.1 12 20.5c-2.3-2.4-3.4-5.4-3.4-8.5S9.7 5.9 12 3.5z"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5.5V19"/><path d="M12 6.4a3 3 0 0 0-5.6-1.2A2.6 2.6 0 0 0 4 8a2.7 2.7 0 0 0 .9 4.4A2.8 2.8 0 0 0 6.6 18c.6 1.6 2.2 2.2 3.6 1.6"/><path d="M12 6.4a3 3 0 0 1 5.6-1.2A2.6 2.6 0 0 1 20 8a2.7 2.7 0 0 1-.9 4.4A2.8 2.8 0 0 1 17.4 18c-.6 1.6-2.2 2.2-3.6 1.6"/></svg>',
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h3.6a2 2 0 0 1 1.5.7l1 1.3H19a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 18H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M9.5 12.2l2.5 2.6 2.5-2.6"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9.2" y="3.5" width="5.6" height="10" rx="2.8"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19.5V5.5M6 11.5l6-6 6 6"/></svg>'
  };

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // 极简富文本：转义 -> 加粗 -> 列表行（后端答案为纯文本，避免 XSS）
  function renderAnswer(text) {
    var safe = escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return safe.split('\n').map(function (line) {
      var bullet = line.match(/^\s*[-·•]\s+(.*)$/);
      if (bullet) {
        return '<div class="md-li"><i>·</i><span>' + bullet[1] + '</span></div>';
      }
      if (!line.trim()) return '<div>&nbsp;</div>';
      return '<div>' + line + '</div>';
    }).join('');
  }

  function pad2(value) {
    var n = parseInt(value, 10);
    if (isNaN(n)) return String(value);
    return n < 10 ? '0' + n : String(n);
  }

  /* ---------------------------------------------------------- 悬浮提问卡 */
  var PromptBox = {
    props: {
      modelValue: { type: String, default: '' },
      busy: { type: Boolean, default: false },
      deep: { type: Boolean, default: false },
      placeholder: { type: String, default: '输入政策名称、条款关键词，或你的问题' }
    },
    emits: ['update:modelValue', 'submit', 'toggle-deep'],
    template: [
      '<form class="prompt-box" :class="{ busy: busy }" @submit.prevent="submit">',
      '  <textarea class="prompt-input" :value="modelValue" :disabled="busy"',
      '    :placeholder="placeholder" rows="1" @input="onInput"',
      '    @keydown.enter.exact.prevent="submit"></textarea>',
      '  <div class="prompt-tools">',
      '    <div class="prompt-tools-left">',
      '      <input ref="fileInput" type="file" class="sr-only"',
      '        accept=".pdf,.docx,.txt,.md,.html,.htm" @change="onFileChange" />',
      '      <button type="button" class="tool-btn" :disabled="busy" title="上传政策文件" @click="pickFile">',
      '        <span v-html="icons.paperclip"></span>',
      '      </button>',
      '      <button type="button" class="tool-btn" :disabled="busy" title="到政策搜索页检索当前问题" @click="search">',
      '        <span v-html="icons.globe"></span>',
      '      </button>',
      '      <button type="button" class="tool-btn" :class="{ on: deep }" :disabled="busy"',
      '        title="深入检索：引用 8 条依据" @click="$emit(\'toggle-deep\')">',
      '        <span v-html="icons.brain"></span><span v-if="deep">深入</span>',
      '      </button>',
      '      <button type="button" class="tool-btn" :disabled="busy" title="政策解读与关联" @click="analysis">',
      '        <span v-html="icons.folder"></span>',
      '      </button>',
      '    </div>',
      '    <div class="prompt-tools-right">',
      '      <button type="button" class="tool-btn round" :class="{ on: listening }" :disabled="busy"',
      '        title="语音输入" @click="toggleMic">',
      '        <span v-html="icons.mic"></span>',
      '      </button>',
      '      <button type="submit" class="send-btn" :disabled="!canSend" title="提交问题">',
      '        <span v-html="icons.send"></span>',
      '      </button>',
      '    </div>',
      '  </div>',
      '</form>'
    ].join(''),
    setup: function (props, context) {
      var Vue = global.Vue;
      var fileInput = Vue.ref(null);
      var state = Vue.reactive({ listening: false });
      var recognition = null;

      function onInput(event) {
        context.emit('update:modelValue', event.target.value);
        var el = event.target;
        el.style.height = '0px';
        var height = Math.min(Math.max(el.scrollHeight, 58), 144);
        el.style.height = height + 'px';
      }

      function submit() {
        if (!props.modelValue.trim() || props.busy) return;
        context.emit('submit', props.modelValue.trim());
      }

      function pickFile() {
        if (fileInput.value) fileInput.value.click();
      }

      function onFileChange(event) {
        var file = event.target.files && event.target.files[0];
        event.target.value = '';
        if (!file) return;
        if (!global.appAuth.isAdmin()) {
          global.ElMessage.info('政策文件入库需管理员权限，可先用「政策搜索」查看已入库文件');
          return;
        }
        global.ElMessage.info('已选择《' + file.name + '》，请在「政策文件」页面上传入库');
        global.appRouter.go('manage');
      }

      function search() {
        var q = (props.modelValue || '').trim();
        global.appRouter.go('documents', q ? { tab: 'search', q: q } : { tab: 'search' });
      }

      function analysis() {
        global.appRouter.go('analysis');
      }

      function toggleMic() {
        var Ctor = global.SpeechRecognition || global.webkitSpeechRecognition;
        if (!Ctor) {
          global.ElMessage.info('当前浏览器不支持语音输入，请改用文字提问');
          return;
        }
        if (state.listening && recognition) {
          recognition.stop();
          return;
        }
        recognition = new Ctor();
        recognition.lang = 'zh-CN';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onresult = function (event) {
          var text = event.results[0][0].transcript || '';
          context.emit('update:modelValue', text);
        };
        recognition.onend = function () { state.listening = false; };
        recognition.onerror = function () { state.listening = false; };
        state.listening = true;
        try { recognition.start(); } catch (e) { state.listening = false; }
      }

      return {
        icons: ICONS,
        fileInput: fileInput,
        listening: Vue.computed(function () { return state.listening; }),
        canSend: Vue.computed(function () { return !!props.modelValue.trim() && !props.busy; }),
        onInput: onInput,
        submit: submit,
        pickFile: pickFile,
        onFileChange: onFileChange,
        search: search,
        analysis: analysis,
        toggleMic: toggleMic
      };
    }
  };

  /* ---------------------------------------------------------- 工作台页面 */
  var WorkbenchView = {
    components: { 'prompt-box': PromptBox },

    template: [
      '<div class="wb-page">',
      '  <div class="wb-scroll" ref="scroller">',
      '',
      '    <div v-if="!messages.length" class="wb-empty">',
      '      <div class="wb-inner">',
      '        <div class="wb-head">',
      '          <div class="eyebrow">政策知识库 / EVIDENCE FLOW</div>',
      '          <h1 class="wb-title">把文件，整理成答案。</h1>',
      '          <p class="wb-sub">从政策原文出发，找到能被复核的依据。</p>',
      '        </div>',
      '        <prompt-box v-model="question" :busy="asking" :deep="deep" @submit="ask" @toggle-deep="deep = !deep" />',
      '      </div>',
      '    </div>',
      '',
      '    <div v-else class="wb-inner wb-thread">',
      '      <div v-for="(msg, index) in messages" :key="index" class="wb-item">',
      '',
      '        <template v-if="msg.role === \'user\'">',
      '          <div class="wb-label">问题</div>',
      '          <div class="wb-question">{{ msg.question }}</div>',
      '        </template>',
      '',
      '        <template v-else>',
      '          <div v-if="msg.loading" class="wb-answer">正在检索知识库原文…</div>',
      '          <template v-else>',
      '            <div v-if="msg.refused" class="wb-refuse">证据不足，已拒答：{{ msg.refuse_reason }}</div>',
      '            <div class="wb-answer" v-html="renderAnswer(msg.displayText)"></div>',
      '',
      '            <template v-if="msg.citations && msg.citations.length">',
      '              <div class="wb-label" style="margin-top:22px">证据</div>',
      '              <div class="evidence-list">',
      '                <div v-for="cite in msg.citations" :key="cite.index" class="evidence-row"',
      '                  @click="openBlock(cite.block_id)">',
      '                  <div class="evidence-head">',
      '                    <span class="evidence-no">证据 {{ pad2(cite.index) }}</span>',
      '                    <span class="evidence-title">《{{ cite.document_title }}》{{ cite.article_number }}</span>',
      '                    <span class="evidence-status" :class="{ invalid: cite.validity_status !== \'VALID\' }">',
      '                      {{ validityName(cite.validity_status) }}',
      '                    </span>',
      '                  </div>',
      '                  <div class="evidence-quote">{{ cite.quote }}</div>',
      '                </div>',
      '              </div>',
      '            </template>',
      '',
      '            <div class="wb-actions">',
      '              <span>证据分 {{ msg.evidence_score }}</span>',
      '              <span>耗时 {{ msg.latency_ms }}ms</span>',
      '              <span>{{ msg.llm_backend === "deepseek" ? "DeepSeek 生成" : "原文摘录" }}</span>',
      '              <button class="act-btn" :class="{ on: msg.feedback === \'UP\' }" @click="feedback(msg, \'UP\')">有帮助</button>',
      '              <button class="act-btn" :class="{ on: msg.feedback === \'DOWN\' }" @click="feedback(msg, \'DOWN\')">不准确</button>',
      '              <button class="act-btn" @click="copyAnswer(msg)">复制带出处</button>',
      '            </div>',
      '          </template>',
      '        </template>',
      '      </div>',
      '    </div>',
      '  </div>',
      '',
      '  <div v-if="messages.length" class="wb-dock">',
      '    <prompt-box v-model="question" :busy="asking" :deep="deep" @submit="ask" @toggle-deep="deep = !deep" />',
      '    <div class="prompt-hint">',
      '      <span>答案依据本地政策知识库原文生成，引用可溯源到具体条款</span>',
      '      <span>',
      '        <button class="link-btn" @click="newChat">新对话</button>',
      '        <span style="margin:0 8px;opacity:.5">·</span>',
      '        <button class="link-btn" @click="openHistory">历史问答</button>',
      '      </span>',
      '    </div>',
      '  </div>',
      '',
      '  <el-drawer v-model="historyDrawer" :size="drawerSize" title="历史问答">',
      '    <div v-if="!history.length" class="empty-state"><el-empty description="暂无历史记录" /></div>',
      '    <div v-else>',
      '      <div class="result-item" v-for="item in history" :key="item.id">',
      '        <div class="result-title">{{ item.question }}</div>',
      '        <div class="text-secondary">{{ truncate(item.answer, 140) }}</div>',
      '        <div class="text-caption" style="margin-top:6px">{{ item.created_at }} · {{ item.refused ? "已拒答" : "已作答" }} · 反馈：{{ item.feedback || "未评价" }}</div>',
      '      </div>',
      '      <el-pagination background layout="prev, pager, next" :total="historyTotal" :current-page="historyPage"',
      '        :page-size="10" @current-change="changeHistoryPage" />',
      '    </div>',
      '  </el-drawer>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var scroller = Vue.ref(null);

      var refs = Vue.reactive({
        question: '',
        asking: false,
        deep: false,
        messages: [],
        historyDrawer: false,
        history: [],
        historyTotal: 0,
        historyPage: 1
      });

      function scrollBottom() {
        Vue.nextTick(function () {
          if (scroller.value) {
            scroller.value.scrollTop = scroller.value.scrollHeight;
          }
        });
      }

      function ask(payload) {
        var question = String(payload == null ? refs.question : payload).trim();
        if (!question) {
          global.ElMessage.warning('请输入问题');
          return;
        }
        if (refs.asking) return;

        refs.messages.push({ role: 'user', question: question });
        var answer = Vue.reactive({
          role: 'ai',
          loading: true,
          answer: '',
          displayText: '',
          citations: [],
          refused: false,
          refuse_reason: '',
          evidence_score: 0,
          latency_ms: 0,
          llm_backend: '',
          log_id: '',
          feedback: ''
        });
        refs.messages.push(answer);
        refs.question = '';
        refs.asking = true;
        scrollBottom();

        global.api.qa.ask({
          question: question,
          session_id: global.utils.sessionId(),
          top_k: refs.deep ? 8 : 5,
          operator: 'web',
          filters: { region: global.appRegion.state.value }
        }).then(function (data) {
          answer.loading = false;
          answer.citations = data.citations || [];
          answer.refused = !!data.refused;
          answer.refuse_reason = data.refuse_reason || '';
          answer.evidence_score = data.evidence_score;
          answer.latency_ms = data.latency_ms;
          answer.llm_backend = data.llm_backend || '';
          answer.log_id = data.log_id || '';
          // 直接呈现完整答案：不做"假打字机"逐字动画，避免误导为真实流式生成
          answer.answer = data.answer || '（未生成答案）';
          answer.displayText = answer.answer;
          scrollBottom();
        }).catch(function () {
          answer.loading = false;
          answer.answer = '提问失败，请检查后端服务是否可用后重试。';
          answer.displayText = answer.answer;
          scrollBottom();
        }).then(function () {
          refs.asking = false;
          scrollBottom();
        });
      }

      function newChat() {
        refs.messages = [];
        refs.question = '';
      }

      function feedback(message, value) {
        if (!message.log_id) return;
        global.api.qa.feedback({ log_id: message.log_id, feedback: value, note: '' })
          .then(function () {
            message.feedback = value;
            global.ElMessage.success('感谢反馈');
          })
          .catch(function () {});
      }

      // 复制内容 = 答案正文 + 引用出处（标题 / 条号 / 摘录），粘贴到其他文档时保留来源
      function buildCopyText(message) {
        var parts = [message.answer || ''];
        var cites = message.citations || [];
        if (cites.length) {
          parts.push('');
          parts.push('—— 引用出处（共 ' + cites.length + ' 条）——');
          cites.forEach(function (cite) {
            parts.push('[' + cite.index + '] 《' + (cite.document_title || '未知文件') + '》' + (cite.article_number || ''));
            if (cite.quote) {
              parts.push('    摘录：' + cite.quote);
            }
          });
        }
        return parts.join('\n');
      }

      function copyAnswer(message) {
        var text = buildCopyText(message);
        try {
          if (global.navigator && global.navigator.clipboard) {
            global.navigator.clipboard.writeText(text);
            global.ElMessage.success('已复制回答及引用出处');
            return;
          }
        } catch (e) { /* 降级：无剪贴板权限时忽略 */ }
        global.ElMessage.warning('当前环境不支持复制，请手动选择文本');
      }

      function openHistory() {
        refs.historyDrawer = true;
        loadHistory(1);
      }

      function loadHistory(page) {
        refs.historyPage = page || refs.historyPage;
        global.api.qa.history({ page: refs.historyPage, page_size: 10 })
          .then(function (data) {
            refs.history = data.items || [];
            refs.historyTotal = data.total || 0;
          })
          .catch(function () {});
      }

      return {
        scroller: scroller,
        icons: ICONS,
        question: Vue.computed({
          get: function () { return refs.question; },
          set: function (value) { refs.question = value; }
        }),
        deep: Vue.computed({
          get: function () { return refs.deep; },
          set: function (value) { refs.deep = value; }
        }),
        asking: Vue.computed(function () { return refs.asking; }),
        messages: Vue.computed(function () { return refs.messages; }),
        historyDrawer: Vue.computed({
          get: function () { return refs.historyDrawer; },
          set: function (value) { refs.historyDrawer = value; }
        }),
        history: Vue.computed(function () { return refs.history; }),
        historyTotal: Vue.computed(function () { return refs.historyTotal; }),
        historyPage: Vue.computed(function () { return refs.historyPage; }),
        drawerSize: Vue.computed(function () {
          return global.innerWidth <= 768 ? '100%' : '40%';
        }),
        ask: ask,
        newChat: newChat,
        feedback: feedback,
        copyAnswer: copyAnswer,
        openHistory: openHistory,
        changeHistoryPage: function (page) { loadHistory(page); },
        renderAnswer: renderAnswer,
        pad2: pad2,
        openBlock: function (blockId) {
          global.appRouter.go('documents', { tab: 'search', block: blockId });
        },
        validityName: function (value) { return global.utils.nameOf(global.utils.VALIDITY_NAMES, value); },
        truncate: global.utils.truncate
      };
    }
  };

  global.views = global.views || {};
  global.views.home = WorkbenchView;
})(window);
