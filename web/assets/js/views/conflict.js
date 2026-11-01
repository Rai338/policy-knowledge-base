/* ============================================================
   冲突初筛（UI-014）：任务提交、异步进度、分级结果、证据对照与报告导出
   ============================================================ */
(function (global) {
  'use strict';

  var ConflictView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">政策冲突初筛</div>',
      '      <div class="text-caption">验证性能力：按时效 / 位阶 / 适用主体 / 地域 / 事项口径五维比对，结果为初筛线索</div>',
      '      <div class="text-caption" style="margin-top:4px">当前比对地域：<b>{{ regionName }}</b>（在右上角切换；选中某市仅比对本市+本省上位法+全国文件）</div>',
      '    </div>',
      '    <div class="toolbar">',
      '      <el-select v-model="form.document_ids" multiple filterable collapse-tags collapse-tags-tooltip',
      '        clearable placeholder="选择参与比对的文件（留空为全库）" style="min-width:320px">',
      '        <el-option v-for="item in documents" :key="item.id" :label="item.title" :value="item.id" />',
      '      </el-select>',
      '      <el-select v-model="form.dimensions" multiple collapse-tags clearable placeholder="检测维度（留空为全部）" style="min-width:280px">',
      '        <el-option v-for="item in dimensions" :key="item.code" :label="item.name" :value="item.code" />',
      '      </el-select>',
      '      <el-input v-model="form.name" placeholder="任务名称" style="width:200px" />',
      '      <el-button type="primary" :loading="creating" @click="create">提交检测</el-button>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header"><div class="h2">检测任务</div><el-button size="small" @click="loadTasks">刷新</el-button></div>',
      '    <div v-if="!tasks.length" class="empty-state"><el-empty description="暂无检测任务" /></div>',
      '    <el-table v-else :data="tasks" border stripe style="width:100%">',
      '      <el-table-column prop="name" label="任务" min-width="180" show-overflow-tooltip />',
      '      <el-table-column label="状态" width="100">',
      '        <template #default="scope"><span class="tag-chip" :class="taskStatusClass(scope.row.status)">{{ taskStatusName(scope.row.status) }}</span></template>',
      '      </el-table-column>',
      '      <el-table-column label="进度" width="200">',
      '        <template #default="scope">',
      '          <el-progress :percentage="scope.row.progress" :status="scope.row.status === \'FAILED\' ? \'exception\' : (scope.row.progress === 100 ? \'success\' : \'\')" />',
      '        </template>',
      '      </el-table-column>',
      '      <el-table-column label="比对组合" width="120">',
      '        <template #default="scope">{{ scope.row.done_pairs }}/{{ scope.row.total_pairs }}</template>',
      '      </el-table-column>',
      '      <el-table-column prop="finding_count" label="发现" width="90" />',
      '      <el-table-column prop="created_at" label="创建时间" width="170" />',
      '      <el-table-column label="操作" width="200" fixed="right">',
      '        <template #default="scope">',
      '          <el-button size="small" @click="openTask(scope.row.id)">查看结果</el-button>',
      '          <el-button size="small" @click="download(scope.row.id)">导出报告</el-button>',
      '        </template>',
      '      </el-table-column>',
      '    </el-table>',
      '    <el-pagination background layout="total, prev, pager, next" :total="tasksTotal" :current-page="tasksPage"',
      '      :page-size="10" @current-change="loadTasks" style="margin-top:12px" v-if="tasksTotal" />',
      '  </div>',
      '',
      '  <el-drawer v-model="drawer" :size="drawerSize" title="冲突检测结果">',
      '    <div v-if="!current" class="empty-state">请选择任务</div>',
      '    <div v-else>',
      '      <div class="h2">{{ current.name }}</div>',
      '      <div class="text-caption" style="margin:6px 0 12px">',
      '        {{ taskStatusName(current.status) }} · 比对 {{ current.done_pairs }}/{{ current.total_pairs }} 对 · 发现 {{ current.finding_count }} 条',
      '      </div>',
      '      <div v-if="!current.findings.length" class="empty-state">',
      '        <el-empty description="未发现冲突线索" />',
      '      </div>',
      '      <div v-for="finding in current.findings" :key="finding.id" class="conflict-item" :class="finding.level">',
      '        <div class="result-meta">',
      '          <span class="tag-chip">{{ finding.dimension_name }}</span>',
      '          <span class="tag-chip" :class="levelClass(finding.level)">{{ levelName(finding.level) }}</span>',
      '        </div>',
      '        <div style="margin:6px 0">{{ finding.reason }}</div>',
      '        <div class="text-secondary" style="margin-bottom:6px">建议：{{ finding.suggestion }}</div>',
      '        <div class="card" style="box-shadow:none;background:var(--color-bg)">',
      '          <div class="text-caption">依据 A：{{ finding.block_a.title }} {{ finding.block_a.article_number || "" }}</div>',
      '          <div class="block-quote">{{ finding.block_a.text }}</div>',
      '          <div class="text-caption" style="margin-top:6px">依据 B：{{ finding.block_b.title }} {{ finding.block_b.article_number || "" }}</div>',
      '          <div class="block-quote">{{ finding.block_b.text }}</div>',
      '        </div>',
      '        <div class="toolbar" style="margin:8px 0 0">',
      '          <el-button size="small" @click="openBlock(finding.block_a.block_id)">查看 A 原文</el-button>',
      '          <el-button size="small" @click="openBlock(finding.block_b.block_id)">查看 B 原文</el-button>',
      '        </div>',
      '      </div>',
      '      <div class="text-caption" style="margin-top:12px">',
      '        说明：本结果为规则初筛（PoC），不构成法律意见，正式适用前须经主管部门确认。',
      '      </div>',
      '    </div>',
      '  </el-drawer>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        documents: [],
        dimensions: [],
        tasks: [],
        tasksTotal: 0,
        tasksPage: 1,
        loading: false,
        creating: false,
        drawer: false,
        current: null,
        form: { document_ids: [], dimensions: [], name: '冲突检测任务' },
        timer: null
      });

      var LEVEL_NAMES = { SUSPECTED: '疑似冲突', POTENTIAL: '潜在冲突', NONE: '未发现冲突' };

      function loadDocuments() {
        global.api.documents.list({ page: 1, page_size: 100, region: global.appRegion.state.value })
          .then(function (data) { refs.documents = data.items || []; })
          .catch(function () {});
      }

      function loadDimensions() {
        global.api.conflict.dimensions()
          .then(function (data) { refs.dimensions = data; })
          .catch(function () {});
      }

      function loadTasks(page) {
        refs.tasksPage = page || refs.tasksPage;
        refs.loading = true;
        global.api.conflict.list({ page: refs.tasksPage, page_size: 10 })
          .then(function (data) {
            refs.tasks = data.items || [];
            refs.tasksTotal = data.total || 0;
          })
          .catch(function () { refs.tasks = []; })
          .then(function () { refs.loading = false; });
      }

      function create() {
        refs.creating = true;
        global.api.conflict.create({
          name: refs.form.name,
          document_ids: refs.form.document_ids,
          dimensions: refs.form.dimensions,
          region: global.appRegion.state.value
        }).then(function (data) {
          global.ElMessage.success('任务已提交，正在比对');
          var taskId = data.id;
          loadTasks(1);
          poll(taskId);
        }).catch(function () {}).then(function () { refs.creating = false; });
      }

      function poll(taskId) {
        stopPoll();
        refs.timer = global.setInterval(function () {
          global.api.conflict.get(taskId, { silent: true })
            .then(function (data) {
              refs.current = data;
              loadTasks(refs.tasksPage);
              if (data.status === 'SUCCESS' || data.status === 'FAILED') {
                stopPoll();
                global.ElNotification.success({
                  title: '检测完成',
                  message: '发现 ' + data.finding_count + ' 条冲突线索'
                });
              }
            })
            .catch(function () { stopPoll(); });
        }, 2000);
      }

      function stopPoll() {
        if (refs.timer) {
          global.clearInterval(refs.timer);
          refs.timer = null;
        }
      }

      function openTask(taskId) {
        refs.drawer = true;
        refs.current = null;
        global.api.conflict.get(taskId)
          .then(function (data) {
            refs.current = data;
            if (data.status === 'PENDING' || data.status === 'RUNNING') poll(taskId);
          })
          .catch(function () { refs.current = null; });
      }

      function download(taskId) {
        global.api.conflict.exportReport(taskId)
          .then(function () {
            global.ElMessage.success('报告已生成，开始下载');
            global.open(global.api.conflict.downloadUrl(taskId));
          })
          .catch(function () {});
      }

      Vue.onMounted(function () {
        loadDocuments();
        loadDimensions();
        loadTasks(1);
        // 地区切换：刷新可选文件列表与任务列表（冲突比对按地域约束）
        Vue.watch(function () { return global.appRegion.state.value; }, function () {
          loadDocuments();
          loadTasks(1);
        });
      });
      Vue.onUnmounted(stopPoll);

      return {
        documents: Vue.computed(function () { return refs.documents; }),
        dimensions: Vue.computed(function () { return refs.dimensions; }),
        tasks: Vue.computed(function () { return refs.tasks; }),
        tasksTotal: Vue.computed(function () { return refs.tasksTotal; }),
        tasksPage: Vue.computed(function () { return refs.tasksPage; }),
        loading: Vue.computed(function () { return refs.loading; }),
        creating: Vue.computed(function () { return refs.creating; }),
        drawer: Vue.computed({
          get: function () { return refs.drawer; },
          set: function (value) {
            refs.drawer = value;
            if (!value) stopPoll();
          }
        }),
        regionName: Vue.computed(function () { return global.appRegion.name(); }),
        current: Vue.computed(function () { return refs.current; }),
        form: Vue.computed(function () { return refs.form; }),
        drawerSize: Vue.computed(function () {
          return global.innerWidth <= 768 ? '100%' : '62%';
        }),
        create: create,
        loadTasks: loadTasks,
        openTask: openTask,
        download: download,
        openBlock: function (blockId) { global.appRouter.go('documents', { tab: 'search', block: blockId }); },
        taskStatusClass: global.utils.taskStatusClass,
        taskStatusName: function (value) { return global.utils.nameOf(global.utils.TASK_STATUS_NAMES, value); },
        levelClass: function (level) {
          return level === 'SUSPECTED' ? 'red' : (level === 'POTENTIAL' ? 'orange' : 'green');
        },
        levelName: function (level) { return LEVEL_NAMES[level] || level; }
      };
    }
  };

  global.views = global.views || {};
  global.views.conflict = ConflictView;
})(window);
