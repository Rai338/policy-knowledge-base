/* ============================================================
   解读与知识关联（UI-013）：摘要、要点解读、术语解释、关联推荐、修订对照、适用判定
   ============================================================ */
(function (global) {
  'use strict';

  var AnalysisView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">政策解读与知识关联</div>',
      '      <div class="text-caption">所有结论均基于知识库原文生成，可回溯至具体条文</div>',
      '    </div>',
      '    <div class="toolbar">',
      '      <el-select v-model="documentId" filterable remote :remote-method="searchDocuments" :loading="docLoading" clearable placeholder="选择政策文件（可搜索）" style="min-width:300px"',
      '        @change="onDocumentChange" @focus="loadDocuments">',
      '        <el-option v-for="item in documents" :key="item.id" :label="item.title" :value="item.id" />',
      '      </el-select>',
      '      <el-input v-model="blockId" placeholder="或填写知识块 ID" style="width:240px" clearable />',
      '      <el-button type="primary" :loading="loading" @click="reload">分析</el-button>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <el-tabs v-model="activeTab">',
      '      <el-tab-pane label="政策摘要" name="summary">',
      '        <div v-if="!documentId" class="empty-state"><el-empty description="请先选择政策文件" /></div>',
      '        <div v-else-if="!summary" class="empty-state"><el-empty description="暂无摘要结果" /></div>',
      '        <div v-else>',
      '          <div class="answer-box">{{ summary.summary }}</div>',
      '          <div class="h3" style="margin:16px 0 8px">核心要点</div>',
      '          <div v-for="(point, index) in summary.points" :key="index" class="block-quote" style="margin-bottom:6px">',
      '            {{ index + 1 }}. {{ point }}',
      '          </div>',
      '          <div class="h3" style="margin:16px 0 8px">关键条款</div>',
      '          <div v-for="item in summary.highlights" :key="item.block_id" class="result-item">',
      '            <div class="result-title">{{ item.article_number || "条款" }}</div>',
      '            <div class="result-text">{{ item.text }}</div>',
      '            <el-button size="small" style="margin-top:8px" @click="openBlock(item.block_id)">查看原文</el-button>',
      '          </div>',
      '          <div class="text-caption" style="margin-top:8px">生成方式：{{ summary.mode === "llm" ? "大模型概括" : "规则抽取（未配置大模型）" }}</div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="要点解读" name="interpret">',
      '        <div v-if="!documentId" class="empty-state"><el-empty description="请先选择政策文件" /></div>',
      '        <div v-else-if="!interpret" class="empty-state"><el-empty description="暂无解读结果" /></div>',
      '        <div v-else>',
      '          <div v-for="dimension in interpret.dimensions" :key="dimension.dimension" class="card" style="box-shadow:none">',
      '            <div class="h3">{{ dimension.dimension }}（{{ dimension.items.length }}）</div>',
      '            <div v-if="!dimension.items.length" class="text-caption">未识别到相关内容</div>',
      '            <div v-for="item in dimension.items" :key="item.block_id" class="block-quote" style="margin-bottom:8px;cursor:pointer"',
      '              @click="openBlock(item.block_id)">',
      '              {{ item.article_number }}：{{ item.text }}',
      '            </div>',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="术语解释" name="term">',
      '        <div class="toolbar">',
      '          <el-input v-model="term" placeholder="输入政策术语，如：专精特新" style="width:280px" @keyup.enter="explain" />',
      '          <el-button type="primary" :loading="termLoading" @click="explain">解释</el-button>',
      '        </div>',
      '        <div v-if="!termResult" class="empty-state"><el-empty description="输入术语后查看解释" /></div>',
      '        <div v-else>',
      '          <div class="answer-box">{{ termResult.explanation }}</div>',
      '          <div class="h3" style="margin:16px 0 8px">出处</div>',
      '          <div v-for="item in termResult.evidence" :key="item.block_id" class="block-quote" style="margin-bottom:8px;cursor:pointer"',
      '            @click="openBlock(item.block_id)">',
      '            《{{ item.document_title }}》{{ item.article_number }}：{{ item.text }}',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="关联政策" name="related">',
      '        <div v-if="!related" class="empty-state"><el-empty description="选择文件或填写知识块 ID 后查看关联" /></div>',
      '        <div v-else>',
      '          <div class="text-caption" style="margin-bottom:8px">上位法引用：{{ (related.higher_law || []).join("、") || "未识别" }}</div>',
      '          <div v-for="match in related.higher_matches" :key="match.document_id" class="result-item">',
      '            <div class="result-title" @click="openDocument(match.document_id)" style="cursor:pointer">{{ match.title }}</div>',
      '            <div class="result-meta"><span class="tag-chip">{{ match.effect_level_name }}</span><span class="tag-chip gray">{{ match.relation }}</span></div>',
      '          </div>',
      '          <div v-for="item in related.items" :key="item.block_id" class="result-item">',
      '            <div class="result-title" @click="openBlock(item.block_id)" style="cursor:pointer">{{ item.title }}</div>',
      '            <div class="result-meta">',
      '              <span class="tag-chip">{{ item.effect_level_name }}</span>',
      '              <span class="tag-chip gray">{{ item.relation }}</span>',
      '              <span class="text-caption">相似度 {{ item.score.toFixed(3) }}</span>',
      '            </div>',
      '            <div class="result-text">{{ truncate(item.original_text, 180) }}</div>',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="修订对照" name="compare">',
      '        <div v-if="!documentId" class="empty-state"><el-empty description="请先选择政策文件" /></div>',
      '        <div v-else-if="!compare" class="empty-state"><el-empty description="暂无版本数据" /></div>',
      '        <div v-else>',
      '          <div class="h3">{{ compare.document.title }}</div>',
      '          <div v-for="version in compare.versions" :key="version.id" class="result-item">',
      '            <div class="result-title">{{ version.version_label }}',
      '              <span class="tag-chip green" v-if="version.is_current">当前版本</span>',
      '            </div>',
      '            <div class="text-secondary">{{ version.change_note || "—" }} · {{ version.created_at }}</div>',
      '          </div>',
      '          <div class="text-caption">当前版本知识块数 {{ compare.diff.current_block_count }}，差异比对基于内容 hash 集合。</div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="适用判定" name="applicability">',
      '        <div class="toolbar">',
      '          <el-select v-model="applicability.subject" clearable placeholder="适用主体" style="width:180px">',
      '            <el-option v-for="item in subjectOptions" :key="item" :label="item" :value="item" />',
      '          </el-select>',
      '          <el-select v-model="applicability.region" clearable filterable placeholder="适用地域" style="width:180px">',
      '            <el-option v-for="item in regionOptions" :key="item" :label="item" :value="item" />',
      '          </el-select>',
      '          <el-select v-model="applicability.topic" clearable placeholder="主题领域" style="width:180px">',
      '            <el-option v-for="item in topicOptions" :key="item" :label="item" :value="item" />',
      '          </el-select>',
      '          <el-button type="primary" :loading="applicabilityLoading" @click="judge">判定</el-button>',
      '        </div>',
      '        <div v-if="!applicabilityResult" class="empty-state"><el-empty description="选择条件后查看适用条款" /></div>',
      '        <div v-else>',
      '          <div class="text-caption">匹配到 {{ applicabilityResult.total }} 条适用条款</div>',
      '          <div v-for="item in applicabilityResult.items" :key="item.block_id" class="result-item">',
      '            <div class="result-title" @click="openBlock(item.block_id)" style="cursor:pointer">{{ item.title }}</div>',
      '            <div class="result-meta">',
      '              <span class="tag-chip">{{ item.effect_level_name }}</span>',
      '              <span class="tag-chip" :class="validityClass(item.validity_status)">{{ item.validity_status_name }}</span>',
      '              <span class="tag-chip gray">{{ (item.applicable_subjects || []).join("、") }}</span>',
      '            </div>',
      '            <div class="result-text">{{ truncate(item.original_text, 180) }}</div>',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '    </el-tabs>',
      '  </div>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        documents: [],
        docLoading: false,
        documentId: '',
        blockId: '',
        activeTab: 'summary',
        loading: false,
        summary: null,
        interpret: null,
        term: '',
        termResult: null,
        termLoading: false,
        related: null,
        compare: null,
        applicability: { subject: '', region: '', topic: '' },
        applicabilityResult: null,
        applicabilityLoading: false,
        subjectOptions: [],
        regionOptions: [],
        topicOptions: []
      });

      function loadDocuments() {
        refs.docLoading = true;
        global.api.documents.list({ page: 1, page_size: 50 })
          .then(function (data) { refs.documents = data.items || []; })
          .catch(function () {})
          .then(function () { refs.docLoading = false; });
      }

      function searchDocuments(query) {
        refs.docLoading = true;
        var params = { page: 1, page_size: 50 };
        if (query && query.trim()) params.keyword = query.trim();
        global.api.documents.list(params)
          .then(function (data) { refs.documents = data.items || []; })
          .catch(function () {})
          .then(function () { refs.docLoading = false; });
      }

      function loadOptions() {
        global.api.admin.options().then(function (data) {
          refs.subjectOptions = data.subject || [];
          refs.regionOptions = (data.jurisdiction || []).slice(0, 40);
          refs.topicOptions = (data.topic || []).slice(0, 40);
        }).catch(function () {});
      }

      function loadSummary() {
        if (!refs.documentId) { refs.summary = null; return Promise.resolve(); }
        return global.api.analysis.summary(refs.documentId)
          .then(function (data) { refs.summary = data; })
          .catch(function () { refs.summary = null; });
      }

      function loadInterpret() {
        if (!refs.documentId) { refs.interpret = null; return Promise.resolve(); }
        return global.api.analysis.interpret(refs.documentId)
          .then(function (data) { refs.interpret = data; })
          .catch(function () { refs.interpret = null; });
      }

      function loadRelated() {
        if (!refs.documentId && !refs.blockId) { refs.related = null; return Promise.resolve(); }
        return global.api.analysis.related({
          document_id: refs.documentId,
          block_id: refs.blockId,
          top_k: 8
        }).then(function (data) { refs.related = data; }).catch(function () { refs.related = null; });
      }

      function loadCompare() {
        if (!refs.documentId) { refs.compare = null; return Promise.resolve(); }
        return global.api.analysis.compare(refs.documentId)
          .then(function (data) { refs.compare = data; })
          .catch(function () { refs.compare = null; });
      }

      function reload() {
        refs.loading = true;
        Promise.all([loadSummary(), loadInterpret(), loadRelated(), loadCompare()])
          .catch(function () {})
          .then(function () { refs.loading = false; });
      }

      function onDocumentChange() {
        refs.blockId = '';
        reload();
      }

      function explain() {
        if (!refs.term.trim()) {
          global.ElMessage.warning('请输入术语');
          return;
        }
        refs.termLoading = true;
        global.api.analysis.term(refs.term)
          .then(function (data) { refs.termResult = data; })
          .catch(function () { refs.termResult = null; })
          .then(function () { refs.termLoading = false; });
      }

      function judge() {
        refs.applicabilityLoading = true;
        global.api.analysis.applicability({
          subject: refs.applicability.subject,
          region: refs.applicability.region,
          topic: refs.applicability.topic,
          page_size: 20
        }).then(function (data) { refs.applicabilityResult = data; })
          .catch(function () { refs.applicabilityResult = null; })
          .then(function () { refs.applicabilityLoading = false; });
      }

      Vue.onMounted(function () {
        loadDocuments();
        loadOptions();
        var documentId = global.appRouter.getQuery('document_id');
        var blockId = global.appRouter.getQuery('block_id');
        var tab = global.appRouter.getQuery('tab');
        if (documentId) refs.documentId = documentId;
        if (blockId) { refs.blockId = blockId; refs.activeTab = 'related'; }
        if (tab) refs.activeTab = tab;
        if (documentId || blockId) reload();
      });

      return {
        documents: Vue.computed(function () { return refs.documents; }),
        docLoading: Vue.computed(function () { return refs.docLoading; }),
        documentId: Vue.computed({
          get: function () { return refs.documentId; },
          set: function (value) { refs.documentId = value; }
        }),
        blockId: Vue.computed({
          get: function () { return refs.blockId; },
          set: function (value) { refs.blockId = value; }
        }),
        activeTab: Vue.computed({
          get: function () { return refs.activeTab; },
          set: function (value) { refs.activeTab = value; }
        }),
        loading: Vue.computed(function () { return refs.loading; }),
        summary: Vue.computed(function () { return refs.summary; }),
        interpret: Vue.computed(function () { return refs.interpret; }),
        term: Vue.computed({
          get: function () { return refs.term; },
          set: function (value) { refs.term = value; }
        }) ,
        termResult: Vue.computed(function () { return refs.termResult; }),
        termLoading: Vue.computed(function () { return refs.termLoading; }),
        related: Vue.computed(function () { return refs.related; }),
        compare: Vue.computed(function () { return refs.compare; }),
        applicability: Vue.computed(function () { return refs.applicability; }),
        applicabilityResult: Vue.computed(function () { return refs.applicabilityResult; }),
        applicabilityLoading: Vue.computed(function () { return refs.applicabilityLoading; }),
        subjectOptions: Vue.computed(function () { return refs.subjectOptions; }),
        regionOptions: Vue.computed(function () { return refs.regionOptions; }),
        topicOptions: Vue.computed(function () { return refs.topicOptions; }),
        loadDocuments: loadDocuments,
        searchDocuments: searchDocuments,
        onDocumentChange: onDocumentChange,
        reload: reload,
        explain: explain,
        judge: judge,
        openBlock: function (blockId) { global.appRouter.go('documents', { tab: 'search', block: blockId }); },
        openDocument: function (documentId) { global.appRouter.go('documents', { id: documentId }); },
        validityClass: global.utils.validityClass,
        truncate: global.utils.truncate
      };
    }
  };

  global.views = global.views || {};
  global.views.analysis = AnalysisView;
})(window);
