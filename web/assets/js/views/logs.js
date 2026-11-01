/* ============================================================
   日志审计（LOG-001～003）：操作日志、检索日志、问答日志
   ============================================================ */
(function (global) {
  'use strict';

  var LogsView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">操作日志与审计</div>',
      '      <div class="text-caption">全过程留痕，支持按类型筛选与按目标检索</div>',
      '    </div>',
      '    <div class="stat-grid" v-loading="summaryLoading">',
      '      <div class="stat-card"><div class="stat-label">日志总数</div><div class="stat-value">{{ summary.total_operations }}</div></div>',
      '      <div class="stat-card"><div class="stat-label">今日操作</div><div class="stat-value">{{ summary.today_operations }}</div></div>',
      '      <div class="stat-card"><div class="stat-label">操作类型</div><div class="stat-value">{{ actionCount }}</div></div>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card">',
      '    <el-tabs v-model="activeTab">',
      '      <el-tab-pane label="操作日志" name="operations">',
      '        <div class="toolbar">',
      '          <el-select v-model="filters.action" clearable placeholder="操作类型" style="width:170px" @change="loadOperations(1)">',
      '            <el-option v-for="(name, code) in actionNames" :key="code" :label="name" :value="code" />',
      '          </el-select>',
      '          <el-input v-model="filters.keyword" placeholder="目标 ID 关键词" style="width:220px" clearable @keyup.enter="loadOperations(1)" />',
      '          <el-date-picker v-model="filters.start" type="date" value-format="YYYY-MM-DD" placeholder="起始日期" style="width:150px" @change="loadOperations(1)" />',
      '          <el-date-picker v-model="filters.end" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" style="width:150px" @change="loadOperations(1)" />',
      '          <el-button :loading="loading" @click="loadOperations(1)">查询</el-button>',
      '        </div>',
      '        <div v-loading="loading">',
      '          <div v-if="!operations.length" class="empty-state"><el-empty description="暂无操作日志" /></div>',
      '          <el-table v-else :data="operations" border stripe style="width:100%">',
      '            <el-table-column prop="action_name" label="操作" width="120" />',
      '            <el-table-column prop="target_type" label="对象类型" width="130" />',
      '            <el-table-column prop="target_id" label="对象 ID" min-width="180" show-overflow-tooltip />',
      '            <el-table-column prop="operator" label="操作人" width="110" />',
      '            <el-table-column label="详情" min-width="220" show-overflow-tooltip>',
      '              <template #default="scope"><el-button size="small" @click="openDetail(scope.row.detail)">查看</el-button></template>',
      '            </el-table-column>',
      '            <el-table-column prop="created_at" label="时间" width="170" />',
      '          </el-table>',
      '          <el-pagination background layout="total, prev, pager, next" :total="operationsTotal"',
      '            :current-page="operationsPage" :page-size="20" @current-change="loadOperations" style="margin-top:12px" v-if="operationsTotal" />',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="检索日志" name="search">',
      '        <div v-loading="searchLoading">',
      '          <div v-if="!searchLogs.length" class="empty-state"><el-empty description="暂无检索记录" /></div>',
      '          <el-table v-else :data="searchLogs" border stripe style="width:100%">',
      '            <el-table-column prop="keyword" label="检索词" min-width="200" show-overflow-tooltip />',
      '            <el-table-column prop="result_count" label="结果数" width="100" />',
      '            <el-table-column prop="latency_ms" label="耗时(ms)" width="110" />',
      '            <el-table-column label="筛选条件" min-width="220" show-overflow-tooltip>',
      '              <template #default="scope"><el-button size="small" @click="openDetail(scope.row.filters)">查看</el-button></template>',
      '            </el-table-column>',
      '            <el-table-column prop="created_at" label="时间" width="170" />',
      '          </el-table>',
      '          <el-pagination background layout="total, prev, pager, next" :total="searchTotal"',
      '            :current-page="searchPage" :page-size="20" @current-change="loadSearchLogs" style="margin-top:12px" v-if="searchTotal" />',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="问答日志" name="qa">',
      '        <div class="toolbar">',
      '          <el-select v-model="qaRefused" clearable placeholder="是否拒答" style="width:150px" @change="loadQaLogs(1)">',
      '            <el-option label="已拒答" value="true" />',
      '            <el-option label="已作答" value="false" />',
      '          </el-select>',
      '          <el-button :loading="qaLoading" @click="loadQaLogs(1)">查询</el-button>',
      '        </div>',
      '        <div v-loading="qaLoading">',
      '          <div v-if="!qaLogs.length" class="empty-state"><el-empty description="暂无问答记录" /></div>',
      '          <div v-for="item in qaLogs" :key="item.id" class="result-item">',
      '            <div class="result-title">{{ item.question }}</div>',
      '            <div class="text-secondary">{{ truncate(item.answer, 180) }}</div>',
      '            <div class="result-meta" style="margin-top:8px">',
      '              <span class="tag-chip" :class="item.refused ? \'red\' : \'green\'">{{ item.refused ? "已拒答" : "已作答" }}</span>',
      '              <span class="tag-chip gray">{{ item.llm_backend === "deepseek" ? "DeepSeek" : "原文摘录" }}</span>',
      '              <span class="tag-chip gray" v-if="item.feedback">{{ item.feedback === "UP" ? "反馈：有帮助" : "反馈：不准确" }}</span>',
      '              <span class="text-caption">证据分 {{ item.evidence_score }} · {{ item.latency_ms }}ms · {{ item.created_at }}</span>',
      '            </div>',
      '            <div v-if="item.citations && item.citations.length" class="text-caption">引用 {{ item.citations.length }} 条来源</div>',
      '          </div>',
      '          <el-pagination background layout="total, prev, pager, next" :total="qaTotal"',
      '            :current-page="qaPage" :page-size="20" @current-change="loadQaLogs" style="margin-top:12px" v-if="qaTotal" />',
      '        </div>',
      '      </el-tab-pane>',
      '    </el-tabs>',
      '  </div>',
      '  <el-dialog title="详情（JSON）" v-model="detailDialogVisible" width="680px">',
      '    <pre class="json-pre">{{ detailJson }}</pre>',
      '  </el-dialog>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        activeTab: 'operations',
        summary: {},
        summaryLoading: false,
        detailDialogVisible: false,
        detailJson: '',
        actionNames: {},
        operations: [],
        operationsTotal: 0,
        operationsPage: 1,
        loading: false,
        filters: { action: '', keyword: '', start: '', end: '' },
        searchLogs: [],
        searchTotal: 0,
        searchPage: 1,
        searchLoading: false,
        qaLogs: [],
        qaTotal: 0,
        qaPage: 1,
        qaLoading: false,
        qaRefused: ''
      });

      function loadSummary() {
        refs.summaryLoading = true;
        global.api.logs.summary()
          .then(function (data) {
            refs.summary = data;
            refs.actionNames = data.action_names || {};
          })
          .catch(function () {})
          .then(function () { refs.summaryLoading = false; });
      }

      function loadOperations(page) {
        refs.operationsPage = page || refs.operationsPage;
        refs.loading = true;
        global.api.logs.operations({
          action: refs.filters.action,
          keyword: refs.filters.keyword,
          start: refs.filters.start,
          end: refs.filters.end,
          page: refs.operationsPage,
          page_size: 20
        }).then(function (data) {
          refs.operations = data.items || [];
          refs.operationsTotal = data.total || 0;
        }).catch(function () {
          refs.operations = [];
        }).then(function () { refs.loading = false; });
      }

      function loadSearchLogs(page) {
        refs.searchPage = page || refs.searchPage;
        refs.searchLoading = true;
        global.api.logs.search({ page: refs.searchPage, page_size: 20 })
          .then(function (data) {
            refs.searchLogs = data.items || [];
            refs.searchTotal = data.total || 0;
          })
          .catch(function () { refs.searchLogs = []; })
          .then(function () { refs.searchLoading = false; });
      }

      function loadQaLogs(page) {
        refs.qaPage = page || refs.qaPage;
        refs.qaLoading = true;
        global.api.logs.qa({
          page: refs.qaPage,
          page_size: 20,
          refused: refs.qaRefused
        }).then(function (data) {
          refs.qaLogs = data.items || [];
          refs.qaTotal = data.total || 0;
        }).catch(function () { refs.qaLogs = []; }).then(function () { refs.qaLoading = false; });
      }

      function openDetail(obj) {
        try {
          refs.detailJson = JSON.stringify(obj, null, 2);
        } catch (error) {
          refs.detailJson = String(obj);
        }
        refs.detailDialogVisible = true;
      }

      Vue.onMounted(function () {
        loadSummary();
        loadOperations(1);
        loadSearchLogs(1);
        loadQaLogs(1);
      });

      return {
        activeTab: Vue.computed({
          get: function () { return refs.activeTab; },
          set: function (value) { refs.activeTab = value; }
        }),
        summary: Vue.computed(function () { return refs.summary; }),
        summaryLoading: Vue.computed(function () { return refs.summaryLoading; }),
        actionNames: Vue.computed(function () { return refs.actionNames; }),
        actionCount: Vue.computed(function () {
          return Object.keys(refs.summary.by_action || {}).length;
        }),
        operations: Vue.computed(function () { return refs.operations; }),
        operationsTotal: Vue.computed(function () { return refs.operationsTotal; }),
        operationsPage: Vue.computed(function () { return refs.operationsPage; }),
        loading: Vue.computed(function () { return refs.loading; }),
        filters: Vue.computed(function () { return refs.filters; }),
        searchLogs: Vue.computed(function () { return refs.searchLogs; }),
        searchTotal: Vue.computed(function () { return refs.searchTotal; }),
        searchPage: Vue.computed(function () { return refs.searchPage; }),
        searchLoading: Vue.computed(function () { return refs.searchLoading; }),
        qaLogs: Vue.computed(function () { return refs.qaLogs; }),
        qaTotal: Vue.computed(function () { return refs.qaTotal; }),
        qaPage: Vue.computed(function () { return refs.qaPage; }),
        qaLoading: Vue.computed(function () { return refs.qaLoading; }),
        qaRefused: Vue.computed({
          get: function () { return refs.qaRefused; },
          set: function (value) { refs.qaRefused = value; }
        }),
        loadOperations: loadOperations,
        loadSearchLogs: loadSearchLogs,
        loadQaLogs: loadQaLogs,
        detailText: function (detail) {
          if (!detail) return '—';
          try {
            return JSON.stringify(detail);
          } catch (error) {
            return String(detail);
          }
        },
        openDetail: openDetail,
        detailDialogVisible: Vue.computed({
          get: function () { return refs.detailDialogVisible; },
          set: function (value) { refs.detailDialogVisible = value; }
        }),
        detailJson: Vue.computed(function () { return refs.detailJson; }),
        truncate: global.utils.truncate
      };
    }
  };

  global.views = global.views || {};
  global.views.logs = LogsView;
})(window);
