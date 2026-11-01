/* ============================================================
   实时采集（UI-011/012）：信源管理、分级调度、手动采集、采集台账与告警
   ============================================================ */
(function (global) {
  'use strict';

  var CrawlView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">实时采集</div>',
      '      <div class="text-caption">分级轮询：核心源 5 分钟 / 一般源 30 分钟 / 长尾源每日</div>',
      '    </div>',
      '    <div class="stat-grid">',
      '      <div class="stat-card"><div class="stat-label">信源总数</div><div class="stat-value">{{ stats.total_sources }}</div><div class="stat-extra">启用中 {{ stats.enabled_sources }}</div></div>',
      '      <div class="stat-card"><div class="stat-label">今日新增/更新</div><div class="stat-value">{{ stats.new_today }}</div><div class="stat-extra">已入库 {{ stats.crawled_documents }} 份</div></div>',
      '      <div class="stat-card"><div class="stat-label">失败记录</div><div class="stat-value" style="color:var(--color-danger)">{{ stats.failed_records }}</div><div class="stat-extra">可在台账中查看原因</div></div>',
      '      <div class="stat-card"><div class="stat-label">调度任务</div><div class="stat-value">{{ jobs.length }}</div><div class="stat-extra">{{ schedulerRunning ? "调度运行中" : "调度未启动" }}</div></div>',
      '    </div>',
      '    <div class="toolbar" style="margin-top:16px">',
      '      <el-button type="primary" :loading="runAllLoading" @click="runAll">立即采集全部信源</el-button>',
      '      <el-button @click="syncJobs">同步调度任务</el-button>',
      '      <el-button @click="openCreate">新增信源</el-button>',
      '      <el-button :loading="loading" @click="loadSources">刷新</el-button>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header"><div class="h2">采集信源</div></div>',
      '    <div v-if="!sources.length" class="empty-state">',
      '      <el-empty description="暂无信源，点击「新增信源」录入政策发布栏目或 RSS 地址" />',
      '    </div>',
      '    <el-table v-else :data="sources" border stripe style="width:100%">',
      '      <el-table-column prop="name" label="信源名称" min-width="180" />',
      '      <el-table-column prop="url" label="地址" min-width="220" show-overflow-tooltip />',
      '      <el-table-column prop="source_type" label="类型" width="90" />',
      '      <el-table-column label="频率" width="120">',
      '        <template #default="scope">{{ scope.row.frequency_name }}（{{ scope.row.frequency_minutes }} 分钟）</template>',
      '      </el-table-column>',
      '      <el-table-column label="最近状态" width="110">',
      '        <template #default="scope">',
      '          <span class="tag-chip" :class="crawlStatusClass(scope.row.last_status)">{{ crawlStatusName(scope.row.last_status) }}</span>',
      '        </template>',
      '      </el-table-column>',
      '      <el-table-column prop="last_run_at" label="最近采集" width="160" />',
      '      <el-table-column label="累计" width="110">',
      '        <template #default="scope">发现 {{ scope.row.total_found }} / 入库 {{ scope.row.total_new }}</template>',
      '      </el-table-column>',
      '      <el-table-column label="操作" width="240" fixed="right">',
      '        <template #default="scope">',
      '          <el-button size="small" :loading="scope.row.running" @click="runSource(scope.row)">采集</el-button>',
      '          <el-button size="small" @click="editSource(scope.row)">编辑</el-button>',
      '          <el-button size="small" type="danger" @click="removeSource(scope.row)">删除</el-button>',
      '        </template>',
      '      </el-table-column>',
      '    </el-table>',
      '    <div v-if="scope_last_error" class="text-caption" style="margin-top:8px;color:var(--color-danger)">最近失败原因：{{ scope_last_error }}</div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="recordsLoading">',
      '    <div class="card-header">',
      '      <div class="h2">采集台账</div>',
      '      <div class="toolbar" style="margin:0">',
      '        <el-select v-model="recordFilters.status" clearable placeholder="状态筛选" style="width:140px" @change="loadRecords(1)">',
      '          <el-option v-for="(name, code) in crawlStatusNames" :key="code" :label="name" :value="code" />',
      '        </el-select>',
      '        <el-input v-model="recordFilters.keyword" placeholder="标题关键词" style="width:200px" clearable @keyup.enter="loadRecords(1)" />',
      '        <el-button size="small" @click="loadRecords(1)">查询</el-button>',
      '      </div>',
      '    </div>',
      '    <div v-if="!records.length" class="empty-state"><el-empty description="暂无采集记录" /></div>',
      '    <el-table v-else :data="records" border stripe style="width:100%">',
      '      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />',
      '      <el-table-column prop="source_name" label="信源" width="150" show-overflow-tooltip />',
      '      <el-table-column label="状态" width="100">',
      '        <template #default="scope">',
      '          <span class="tag-chip" :class="crawlStatusClass(scope.row.status)">{{ crawlStatusName(scope.row.status) }}</span>',
      '        </template>',
      '      </el-table-column>',
      '      <el-table-column prop="message" label="说明" min-width="220" show-overflow-tooltip />',
      '      <el-table-column prop="crawled_at" label="采集时间" width="170" />',
      '      <el-table-column label="操作" width="120" fixed="right">',
      '        <template #default="scope">',
      '          <el-button size="small" @click="openDocument(scope.row.document_id)" :disabled="!scope.row.document_id">查看文件</el-button>',
      '        </template>',
      '      </el-table-column>',
      '    </el-table>',
      '    <el-pagination background layout="total, prev, pager, next" :total="recordsTotal" :current-page="recordsPage"',
      '      :page-size="20" @current-change="loadRecords" style="margin-top:12px" v-if="recordsTotal" />',
      '  </div>',
      '',
      '  <el-dialog v-model="sourceDialog" :title="editing ? \'编辑信源\' : \'新增信源\'" width="620px">',
      '    <el-form label-width="110px">',
      '      <el-form-item label="信源名称"><el-input v-model="form.name" placeholder="如：XX省人民政府 政策文件" /></el-form-item>',
      '      <el-form-item label="地址"><el-input v-model="form.url" placeholder="列表页 URL 或 RSS 地址" /></el-form-item>',
      '      <el-form-item label="类型">',
      '        <el-radio-group v-model="form.source_type">',
      '          <el-radio label="LIST">列表页</el-radio>',
      '          <el-radio label="RSS">RSS/Atom</el-radio>',
      '        </el-radio-group>',
      '      </el-form-item>',
      '      <el-form-item label="采集频率">',
      '        <el-select v-model="form.frequency" style="width:100%">',
      '          <el-option label="核心源（5 分钟）" value="CORE" />',
      '          <el-option label="一般源（30 分钟）" value="NORMAL" />',
      '          <el-option label="长尾源（每日）" value="TAIL" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="机构层级">',
      '        <el-select v-model="form.institution_level" style="width:100%">',
      '          <el-option v-for="(name, code) in institutionLevels" :key="code" :label="name" :value="code" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="默认主题">',
      '        <el-select v-model="form.default_topics" multiple style="width:100%">',
      '          <el-option v-for="item in topicOptions" :key="item" :label="item" :value="item" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="列表选择器" v-if="form.source_type === \'LIST\'">',
      '        <el-input v-model="form.list_selector" placeholder="CSS 选择器，默认 a（全部链接）" />',
      '      </el-form-item>',
      '      <el-form-item label="标题关键词">',
      '        <el-input v-model="form.title_keywords" placeholder="逗号分隔，如：通知,办法,意见（留空则不过滤）" />',
      '      </el-form-item>',
      '      <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>',
      '    </el-form>',
      '    <div class="test-zone">',
      '      <div class="test-head">',
      '        <span>测试抓取（保存前预览解析结果）</span>',
      '        <el-button size="small" :loading="testLoading" @click="testSource">测试抓取</el-button>',
      '      </div>',
      '      <div v-if="testResult" class="test-result">',
      '        <div class="text-secondary">{{ testResult.message }}</div>',
      '        <div v-if="testResult.items && testResult.items.length" class="test-items">',
      '          <div v-for="(it, i) in testResult.items.slice(0, 5)" :key="i" class="test-item">',
      '            <span class="test-idx">{{ i + 1 }}</span>',
      '            <span class="test-title">{{ it.title }}</span>',
      '          </div>',
      '          <div v-if="testResult.items.length > 5" class="text-caption">… 其余 {{ testResult.items.length - 5 }} 条见采集结果</div>',
      '        </div>',
      '        <div v-if="testResult.sample" class="test-sample">',
      '          <div class="text-caption">首条正文抽样：{{ testResult.sample.title }}（正文字数 {{ testResult.sample.text_length }}）</div>',
      '          <div v-if="testResult.sample.warning" class="text-caption" style="color:var(--color-danger)">{{ testResult.sample.warning }}</div>',
      '          <div class="block-quote">{{ testResult.sample.snippet || "（未能抽取到正文）" }}</div>',
      '        </div>',
      '      </div>',
      '    </div>',
      '    <template #footer>',
      '      <el-button @click="sourceDialog = false">取消</el-button>',
      '      <el-button type="primary" :loading="saving" @click="submitSource">保存</el-button>',
      '    </template>',
      '  </el-dialog>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        sources: [],
        loading: false,
        runAllLoading: false,
        stats: {},
        jobs: [],
        schedulerRunning: false,
        records: [],
        recordsTotal: 0,
        recordsPage: 1,
        recordFilters: { status: '', keyword: '' },
        recordsLoading: false,
        sourceDialog: false,
        saving: false,
        editing: false,
        editingId: '',
        testLoading: false,
        testResult: null,
        topicOptions: [],
        institutionLevels: {},
        crawlStatusNames: global.utils.CRAWL_STATUS_NAMES,
        form: {
          name: '', url: '', source_type: 'LIST', frequency: 'NORMAL',
          institution_level: 'OTHER', default_topics: [], list_selector: 'a',
          title_keywords: '', enabled: true
        }
      });

      function loadSources() {
        refs.loading = true;
        global.api.crawl.sources({ page: 1, page_size: 100 })
          .then(function (data) {
            refs.sources = (data.items || []).map(function (item) {
              item.running = false;
              return item;
            });
          })
          .catch(function () { refs.sources = []; })
          .then(function () { refs.loading = false; });
      }

      function loadStats() {
        global.api.crawl.stats().then(function (data) { refs.stats = data; }).catch(function () {});
        global.api.crawl.jobs().then(function (data) {
          refs.jobs = data.jobs || [];
          refs.schedulerRunning = data.running;
        }).catch(function () {});
      }

      function loadRecords(page) {
        refs.recordsPage = page || refs.recordsPage;
        refs.recordsLoading = true;
        global.api.crawl.records({
          page: refs.recordsPage,
          page_size: 20,
          status: refs.recordFilters.status,
          keyword: refs.recordFilters.keyword
        }).then(function (data) {
          refs.records = data.items || [];
          refs.recordsTotal = data.total || 0;
        }).catch(function () {
          refs.records = [];
          refs.recordsTotal = 0;
        }).then(function () { refs.recordsLoading = false; });
      }

      function runSource(row) {
        row.running = true;
        global.api.crawl.runSource(row.id)
          .then(function (data) {
            global.ElMessage.success(
              '采集完成：发现 ' + data.found + ' 条，新增 ' + data.new + ' 条，更新 ' + data.updated + ' 条'
            );
            loadSources();
            loadStats();
            loadRecords(1);
          })
          .catch(function () {})
          .then(function () { row.running = false; });
      }

      function runAll() {
        refs.runAllLoading = true;
        global.api.crawl.runAll()
          .then(function (data) {
            global.ElMessage.success('已执行 ' + data.sources + ' 个信源');
            loadSources();
            loadStats();
            loadRecords(1);
          })
          .catch(function () {})
          .then(function () { refs.runAllLoading = false; });
      }

      function syncJobs() {
        global.api.crawl.sync()
          .then(function (data) {
            global.ElMessage.success(data.message);
            loadStats();
          })
          .catch(function () {});
      }

      function editSource(row) {
        refs.editing = true;
        refs.editingId = row.id;
        refs.testResult = null;
        refs.form = {
          name: row.name,
          url: row.url,
          source_type: row.source_type,
          frequency: row.frequency,
          institution_level: row.institution_level,
          default_topics: row.default_topics || [],
          list_selector: row.list_selector,
          title_keywords: row.title_keywords,
          enabled: row.enabled
        };
        refs.sourceDialog = true;
      }

      function removeSource(row) {
        global.ElMessageBox.confirm('确认删除信源「' + row.name + '」？', '删除确认', { type: 'warning' })
          .then(function () { return global.api.crawl.removeSource(row.id); })
          .then(function () {
            global.ElMessage.success('已删除');
            loadSources();
            loadStats();
          })
          .catch(function () {});
      }

      function openCreate() {
        refs.editing = false;
        refs.editingId = '';
        refs.testResult = null;
        refs.form = {
          name: '', url: '', source_type: 'LIST', frequency: 'NORMAL',
          institution_level: 'OTHER', default_topics: [], list_selector: 'a',
          title_keywords: '', enabled: true
        };
        refs.sourceDialog = true;
      }

      function testSource() {
        if (!refs.form.url.trim()) {
          global.ElMessage.warning('请先填写信源地址');
          return;
        }
        refs.testLoading = true;
        refs.testResult = null;
        global.api.crawl.test({
          name: refs.form.name,
          url: refs.form.url,
          source_type: refs.form.source_type,
          frequency: refs.form.frequency,
          institution_level: refs.form.institution_level,
          default_topics: refs.form.default_topics,
          list_selector: refs.form.list_selector,
          title_keywords: refs.form.title_keywords,
          enabled: refs.form.enabled
        }).then(function (data) {
          refs.testResult = data || {};
          if (data && data.ok) {
            global.ElMessage.success(data.message || '测试完成');
          } else {
            global.ElMessage.warning((data && data.message) || '测试未解析到内容');
          }
        }).catch(function () { refs.testResult = null; })
          .then(function () { refs.testLoading = false; });
      }

      function submitSource() {
        if (!refs.form.name.trim() || !refs.form.url.trim()) {
          global.ElMessage.warning('名称与地址不能为空');
          return;
        }
        refs.saving = true;
        var request = refs.editing
          ? global.api.crawl.updateSource(refs.editingId, refs.form)
          : global.api.crawl.createSource(refs.form);
        request.then(function () {
          global.ElMessage.success(refs.editing ? '已更新' : '已新增');
          refs.sourceDialog = false;
          refs.editing = false;
          refs.form = {
            name: '', url: '', source_type: 'LIST', frequency: 'NORMAL',
            institution_level: 'OTHER', default_topics: [], list_selector: 'a',
            title_keywords: '', enabled: true
          };
          loadSources();
          loadStats();
        }).catch(function () {}).then(function () { refs.saving = false; });
      }

      Vue.onMounted(function () {
        loadSources();
        loadStats();
        // 支持从管理员待办概览直达：?status=FAILED 时预置失败筛选
        var presetStatus = global.appRouter.getQuery('status');
        if (presetStatus) {
          refs.recordFilters.status = presetStatus;
        }
        loadRecords(1);
        global.api.meta.options().then(function (data) {
          refs.institutionLevels = data.institution_levels || {};
        }).catch(function () {});
        global.api.admin.options().then(function (data) {
          refs.topicOptions = (data.topic || []).slice(0, 40);
        }).catch(function () {});
      });

      return {
        sources: Vue.computed(function () { return refs.sources; }),
        loading: Vue.computed(function () { return refs.loading; }),
        runAllLoading: Vue.computed(function () { return refs.runAllLoading; }),
        stats: Vue.computed(function () { return refs.stats; }),
        jobs: Vue.computed(function () { return refs.jobs; }),
        schedulerRunning: Vue.computed(function () { return refs.schedulerRunning; }),
        records: Vue.computed(function () { return refs.records; }),
        recordsTotal: Vue.computed(function () { return refs.recordsTotal; }),
        recordsPage: Vue.computed(function () { return refs.recordsPage; }),
        recordFilters: Vue.computed(function () { return refs.recordFilters; }),
        recordsLoading: Vue.computed(function () { return refs.recordsLoading; }),
        sourceDialog: Vue.computed({
          get: function () { return refs.sourceDialog; },
          set: function (value) { refs.sourceDialog = value; }
        }),
        saving: Vue.computed(function () { return refs.saving; }),
        editing: Vue.computed(function () { return refs.editing; }),
        testLoading: Vue.computed(function () { return refs.testLoading; }),
        testResult: Vue.computed(function () { return refs.testResult; }),
        form: Vue.computed(function () { return refs.form; }),
        topicOptions: Vue.computed(function () { return refs.topicOptions; }),
        institutionLevels: Vue.computed(function () { return refs.institutionLevels; }),
        crawlStatusNames: Vue.computed(function () { return refs.crawlStatusNames; }),
        scope_last_error: Vue.computed(function () {
          var failed = refs.sources.filter(function (s) { return s.last_status === 'FAILED' && s.last_error; });
          return failed.length ? failed[0].last_error : '';
        }),
        loadSources: loadSources,
        loadRecords: loadRecords,
        openCreate: openCreate,
        testSource: testSource,
        runSource: runSource,
        runAll: runAll,
        syncJobs: syncJobs,
        editSource: editSource,
        removeSource: removeSource,
        submitSource: submitSource,
        crawlStatusClass: global.utils.crawlStatusClass,
        crawlStatusName: function (value) { return global.utils.nameOf(global.utils.CRAWL_STATUS_NAMES, value); },
        openDocument: function (documentId) {
          if (documentId) global.appRouter.go('documents', { id: documentId });
        }
      };
    }
  };

  global.views = global.views || {};
  global.views.crawl = CrawlView;
})(window);
