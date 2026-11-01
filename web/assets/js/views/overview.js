/* ============================================================
   数据总览（原工作台概览）：统计卡片、近 7 日趋势、知识库构成
   说明：登录后首屏为工作台，概览数据移至本页，便于管理员统一查看
   ============================================================ */
(function (global) {
  'use strict';

  var OverviewView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">数据总览</div>',
      '      <div class="text-caption">数据更新时间：{{ updatedAt || "—" }}</div>',
      '    </div>',
      '    <div class="text-secondary">覆盖采集入库、知识块切分、混合检索、可追溯问答、解读关联与冲突初筛全流程。</div>',
      '    <div class="toolbar" style="margin-top:16px">',
      '      <el-button type="primary" @click="go(\'documents\', { tab: \'search\' })">开始检索</el-button>',
      '      <el-button @click="go(\'home\')">工作台</el-button>',
      '      <el-button @click="go(\'documents\')">政策搜索</el-button>',
      '      <el-button @click="go(\'conflict\')">冲突初筛</el-button>',
      '      <el-button @click="load" :loading="loading">刷新数据</el-button>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="stat-grid" v-loading="loading">',
      '    <div class="stat-card"><div class="stat-label">政策文件</div><div class="stat-value">{{ stats.documents }}</div><div class="stat-extra">今日新增 {{ stats.new_today }}</div></div>',
      '    <div class="stat-card"><div class="stat-label">政策知识块</div><div class="stat-value">{{ stats.blocks }}</div><div class="stat-extra">按条/款粒度切分</div></div>',
      '    <div class="stat-card"><div class="stat-label">问答次数</div><div class="stat-value">{{ stats.qa_total }}</div><div class="stat-extra">拒答 {{ stats.qa_refused }} 次 · 平均 {{ stats.qa_avg_latency_ms }}ms</div></div>',
      '    <div class="stat-card"><div class="stat-label">检索次数</div><div class="stat-value">{{ stats.search_total }}</div><div class="stat-extra">全部留痕可审计</div></div>',
      '    <div class="stat-card"><div class="stat-label">采集信源</div><div class="stat-value">{{ crawl.enabled_sources }}/{{ crawl.total_sources }}</div><div class="stat-extra">今日新增 {{ crawl.new_today }} 条 · 失败 {{ crawl.failed_records }}</div></div>',
      '    <div class="stat-card"><div class="stat-label">冲突发现</div><div class="stat-value">{{ stats.conflict_findings }}</div><div class="stat-extra">来自 {{ stats.conflict_tasks }} 个检测任务</div></div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header"><div class="h2">近 7 日入库与问答趋势</div></div>',
      '    <div v-if="trend.length" style="display:flex;align-items:flex-end;gap:12px;height:150px">',
      '      <div v-for="item in trend" :key="item.date" style="flex:1;text-align:center">',
      '        <div :style="{height: barHeight(item.documents)+ \'px\', background:\'var(--color-primary)\', borderRadius:\'4px 4px 0 0\', minHeight:\'4px\'}"></div>',
      '        <div class="text-caption" style="margin-top:4px">{{ item.date.slice(5) }}</div>',
      '        <div class="text-caption">文{{ item.documents }} · 问{{ item.qa }}</div>',
      '      </div>',
      '    </div>',
      '    <div v-else class="empty-state">暂无趋势数据</div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header"><div class="h2">知识库构成</div></div>',
      '    <div v-if="hasOverview" style="display:flex;gap:24px;flex-wrap:wrap">',
      '      <div>',
      '        <div class="h3" style="margin-bottom:8px">按效力位阶</div>',
      '        <div v-for="(count, key) in overview.by_level" :key="key" class="text-secondary" style="margin-bottom:4px">',
      '          {{ levelName(key) }}：{{ count }}',
      '        </div>',
      '      </div>',
      '      <div>',
      '        <div class="h3" style="margin-bottom:8px">按时效状态</div>',
      '        <div v-for="(count, key) in overview.by_validity" :key="key" class="text-secondary" style="margin-bottom:4px">',
      '          {{ validityName(key) }}：{{ count }}',
      '        </div>',
      '      </div>',
      '      <div>',
      '        <div class="h3" style="margin-bottom:8px">按来源</div>',
      '        <div v-for="(count, key) in overview.by_source" :key="key" class="text-secondary" style="margin-bottom:4px">',
      '          {{ key === "UPLOAD" ? "人工上传" : "自动采集" }}：{{ count }}',
      '        </div>',
      '      </div>',
      '    </div>',
      '    <div v-else class="empty-state">暂无数据，可先在「政策文件」中上传文件或导入示例</div>',
      '    <div class="toolbar" style="margin-top:12px">',
      '      <el-button size="small" @click="importSamples" :loading="sampleLoading">一键导入示例政策</el-button>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        stats: {},
        crawl: {},
        overview: {},
        trend: [],
        loading: false,
        sampleLoading: false,
        updatedAt: ''
      });

      function load() {
        refs.loading = true;
        return Promise.all([
          global.api.dashboard.stats(),
          global.api.dashboard.trend(7),
          global.api.admin.overview()
        ]).then(function (results) {
          refs.stats = results[0] || {};
          refs.crawl = results[0].crawl || {};
          refs.trend = (results[1] && results[1].items) || [];
          refs.overview = results[2] || {};
          refs.updatedAt = new Date().toLocaleString('zh-CN');
        }).catch(function () {
          // 失败提示由 api 层统一弹出
        }).then(function () {
          refs.loading = false;
        });
      }

      function importSamples() {
        refs.sampleLoading = true;
        global.api.documents.importSamples()
          .then(function () {
            global.ElMessage.success('示例政策已导入');
            return load();
          })
          .catch(function () {})
          .then(function () { refs.sampleLoading = false; });
      }

      Vue.onMounted(load);

      return {
        stats: Vue.computed(function () { return refs.stats; }),
        crawl: Vue.computed(function () { return refs.crawl; }),
        overview: Vue.computed(function () { return refs.overview; }),
        trend: Vue.computed(function () { return refs.trend; }),
        loading: Vue.computed(function () { return refs.loading; }),
        sampleLoading: Vue.computed(function () { return refs.sampleLoading; }),
        updatedAt: Vue.computed(function () { return refs.updatedAt; }),
        hasOverview: Vue.computed(function () {
          return Object.keys(refs.overview.by_level || {}).length > 0;
        }),
        barHeight: function (value) {
          var max = Math.max(1, ...refs.trend.map(function (i) { return Math.max(i.documents, i.qa); }));
          return Math.round((value / max) * 100);
        },
        levelName: function (key) { return global.utils.nameOf(global.utils.LEVEL_NAMES, key); },
        validityName: function (key) { return global.utils.nameOf(global.utils.VALIDITY_NAMES, key); },
        go: function (name) { global.appRouter.go(name); },
        load: load,
        importSamples: importSamples
      };
    }
  };

  global.views = global.views || {};
  global.views.overview = OverviewView;
})(window);
