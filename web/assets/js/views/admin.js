/* ============================================================
   管理后台（UI-015）：字典维护、人工复核队列、索引与数据维护
   ============================================================ */
(function (global) {
  'use strict';

  var AdminView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">系统管理</div>',
      '      <div class="text-caption">标签字典、人工复核与索引维护</div>',
      '    </div>',
      '    <div class="todo-grid">',
      '      <div class="todo-card" :class="{ warn: todo.pending_review }" @click="goTodo(\'review\')">',
      '        <div class="todo-label">待复核</div>',
      '        <div class="todo-value">{{ todo.pending_review || 0 }}</div>',
      '        <div class="todo-hint">自动抽取结果待人工确认 →</div>',
      '      </div>',
      '      <div class="todo-card" :class="{ danger: todo.crawl_failed }" @click="goTodo(\'crawl\')">',
      '        <div class="todo-label">采集失败</div>',
      '        <div class="todo-value">{{ todo.crawl_failed || 0 }}</div>',
      '        <div class="todo-hint">采集台账中的失败记录 →</div>',
      '      </div>',
      '      <div class="todo-card" :class="{ danger: todo.parse_failed }" @click="goTodo(\'parse\')">',
      '        <div class="todo-label">解析失败</div>',
      '        <div class="todo-value">{{ todo.parse_failed || 0 }}</div>',
      '        <div class="todo-hint">入库失败的文件 →</div>',
      '      </div>',
      '    </div>',
      '    <el-tabs v-model="activeTab">',
      '      <el-tab-pane label="字典维护" name="dict">',
      '        <div class="toolbar">',
      '          <el-select v-model="dictCategory" clearable placeholder="分类" style="width:180px" @change="loadDict(1)">',
      '            <el-option v-for="(label, value) in categories" :key="value" :label="label" :value="value" />',
      '          </el-select>',
      '          <el-button type="primary" @click="openCreate">新增字典项</el-button>',
      '          <el-button :loading="dictLoading" @click="loadDict(1)">刷新</el-button>',
      '        </div>',
      '        <div v-loading="dictLoading">',
      '          <div v-if="!dictItems.length" class="empty-state"><el-empty description="暂无自定义字典项（内置字典仍可用于筛选）" /></div>',
      '          <el-table v-else :data="dictItems" border stripe style="width:100%">',
      '            <el-table-column prop="category" label="分类" width="140">',
      '              <template #default="scope">{{ categories[scope.row.category] || scope.row.category }}</template>',
      '            </el-table-column>',
      '            <el-table-column prop="name" label="名称" min-width="180" />',
      '            <el-table-column prop="code" label="编码" width="160" />',
      '            <el-table-column label="状态" width="110">',
      '              <template #default="scope">',
      '                <span class="tag-chip" :class="scope.row.enabled ? \'green\' : \'gray\'">{{ scope.row.enabled ? "启用" : "停用" }}</span>',
      '              </template>',
      '            </el-table-column>',
      '            <el-table-column label="操作" width="220" fixed="right">',
      '              <template #default="scope">',
      '                <el-button size="small" @click="toggle(scope.row)">{{ scope.row.enabled ? "停用" : "启用" }}</el-button>',
      '                <el-button size="small" @click="edit(scope.row)">编辑</el-button>',
      '                <el-button size="small" type="danger" @click="remove(scope.row)">删除</el-button>',
      '              </template>',
      '            </el-table-column>',
      '          </el-table>',
      '          <el-pagination background layout="total, prev, pager, next" :total="dictTotal" :current-page="dictPage"',
      '            :page-size="20" @current-change="loadDict" style="margin-top:12px" v-if="dictTotal" />',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="人工复核" name="review">',
      '        <div class="toolbar">',
      '          <el-select v-model="reviewStatus" clearable placeholder="状态" style="width:160px" @change="loadReview(1)">',
      '            <el-option label="待复核" value="PENDING" />',
      '            <el-option label="已确认" value="APPROVED" />',
      '            <el-option label="已驳回" value="REJECTED" />',
      '          </el-select>',
      '          <el-button :loading="reviewLoading" @click="loadReview(1)">刷新</el-button>',
      '        </div>',
      '        <div v-loading="reviewLoading">',
      '          <div v-if="!reviewItems.length" class="empty-state"><el-empty description="暂无待复核项" /></div>',
      '          <div v-for="item in reviewItems" :key="item.id" class="result-item">',
      '            <div class="result-title" @click="openReview(item)" style="cursor:pointer">',
      '              {{ item.target_title || item.target_id }}',
      '            </div>',
      '            <div class="result-meta">',
      '              <span class="tag-chip gray">{{ item.target_type === "BLOCK" ? "知识块" : "文件" }}</span>',
      '              <span class="tag-chip" :class="reviewStatusClass(item.status)">',
      '                {{ reviewStatusName(item.status) }}',
      '              </span>',
      '            </div>',
      '            <div class="text-secondary">复核原因：{{ item.reason }}</div>',
      '            <div class="text-caption" style="margin-top:4px">{{ item.created_at }}</div>',
      '            <div class="toolbar" style="margin:8px 0 0">',
      '              <el-button size="small" type="success" @click="openReview(item)">复核并修正</el-button>',
      '              <el-button size="small" @click="openTarget(item)">查看原文页</el-button>',
      '            </div>',
      '          </div>',
      '          <el-pagination background layout="total, prev, pager, next" :total="reviewTotal" :current-page="reviewPage"',
      '            :page-size="20" @current-change="loadReview" style="margin-top:12px" v-if="reviewTotal" />',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="索引与数据" name="system">',
      '        <div class="stat-grid">',
      '          <div class="stat-card"><div class="stat-label">政策文件</div><div class="stat-value">{{ overview.documents }}</div></div>',
      '          <div class="stat-card"><div class="stat-label">知识块</div><div class="stat-value">{{ overview.blocks }}</div></div>',
      '          <div class="stat-card"><div class="stat-label">向量后端</div><div class="stat-value" style="font-size:20px">{{ (overview.index || {}).vector_backend || "—" }}</div>',
      '            <div class="stat-extra">维度 {{ (overview.index || {}).vector_dim || "—" }}</div>',
      '          </div>',
      '        </div>',
      '        <div class="toolbar" style="margin-top:16px">',
      '          <el-button type="primary" :loading="reindexLoading" @click="reindex">全量重建索引</el-button>',
      '          <el-button :loading="overviewLoading" @click="loadOverview">刷新概览</el-button>',
      '        </div>',
      '        <div class="text-caption" style="margin-top:8px">',
      '          重建索引会重新载入全部知识块，用于数据修复或向量后端切换后的刷新。',
      '        </div>',
      '      </el-tab-pane>',
      '    </el-tabs>',
      '  </div>',
      '',
      '  <el-dialog v-model="dialog" :title="editing ? \'编辑字典项\' : \'新增字典项\'" width="480px">',
      '    <el-form label-width="90px">',
      '      <el-form-item label="分类">',
      '        <el-select v-model="form.category" style="width:100%">',
      '          <el-option v-for="(label, value) in categories" :key="value" :label="label" :value="value" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>',
      '      <el-form-item label="编码"><el-input v-model="form.code" placeholder="可留空，默认与名称一致" /></el-form-item>',
      '      <el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item>',
      '      <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>',
      '    </el-form>',
      '    <template #footer>',
      '      <el-button @click="dialog = false">取消</el-button>',
      '      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>',
      '    </template>',
      '  </el-dialog>',
      '',
      '  <el-drawer v-model="reviewDrawer" :size="drawerSize" title="人工复核 · 原文对照">',
      '    <div v-if="reviewDetail" v-loading="reviewDetailLoading">',
      '      <div class="h2">{{ reviewDetail.target_title || reviewDetail.target_id }}</div>',
      '      <div class="result-meta" style="margin:6px 0">',
      '        <span class="tag-chip gray">{{ reviewDetail.target_type === "BLOCK" ? "知识块" : "文件" }}</span>',
      '        <span class="tag-chip" :class="reviewStatusClass(reviewDetail.status)">{{ reviewStatusName(reviewDetail.status) }}</span>',
      '      </div>',
      '      <div class="text-secondary" style="margin-bottom:12px">复核原因：{{ reviewDetail.reason || "—" }}</div>',
      '      <div class="review-cols">',
      '        <div class="review-col">',
      '          <div class="col-title">原文内容（对照）</div>',
      '          <div v-if="!reviewDetail.blocks.length" class="text-caption">（无知识块原文）</div>',
      '          <div v-for="b in reviewDetail.blocks" :key="b.block_id" class="review-orig">',
      '            <div class="text-caption">{{ b.article_number || (b.structure_path && b.structure_path.join(" / ")) || "正文" }}</div>',
      '            <div class="orig-text">{{ b.original_text }}</div>',
      '          </div>',
      '        </div>',
      '        <div class="review-col">',
      '          <div class="col-title">标签修正（可就地编辑）</div>',
      '          <el-form label-width="80px" size="small" style="margin-top:8px">',
      '            <el-form-item label="适用地区">',
      '              <el-select v-model="reviewForm.jurisdiction" multiple filterable allow-create default-first-option style="width:100%" placeholder="选择或输入地区">',
      '                <el-option v-for="item in dictOptions.jurisdiction" :key="item" :label="item" :value="item" />',
      '              </el-select>',
      '            </el-form-item>',
      '            <el-form-item label="主题领域">',
      '              <el-select v-model="reviewForm.topics" multiple filterable style="width:100%" placeholder="选择主题">',
      '                <el-option v-for="item in dictOptions.topic" :key="item" :label="item" :value="item" />',
      '              </el-select>',
      '            </el-form-item>',
      '            <el-form-item label="适用主体">',
      '              <el-select v-model="reviewForm.applicable_subjects" multiple filterable style="width:100%" placeholder="选择主体">',
      '                <el-option v-for="item in dictOptions.subject" :key="item" :label="item" :value="item" />',
      '              </el-select>',
      '            </el-form-item>',
      '          </el-form>',
      '          <div class="text-caption">修正后点击「一键通过」，将保存标签并确认复核；驳回则不修改标签。</div>',
      '        </div>',
      '      </div>',
      '      <div class="toolbar" style="margin-top:16px">',
      '        <el-button type="success" :loading="reviewSaving" @click="approveWithPatch">一键通过</el-button>',
      '        <el-button type="danger" :loading="reviewSaving" @click="rejectReview">驳回</el-button>',
      '        <el-button @click="reviewDrawer = false">取消</el-button>',
      '      </div>',
      '    </div>',
      '    <div v-else class="empty-state">{{ reviewDetailLoading ? "加载中…" : "请选择复核项" }}</div>',
      '  </el-drawer>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        activeTab: 'dict',
        categories: {
          topic: '主题领域',
          subject: '适用主体',
          jurisdiction: '适用地域',
          level: '效力位阶',
          institution_level: '机构层级'
        },
        dictItems: [],
        dictTotal: 0,
        dictPage: 1,
        dictCategory: '',
        dictLoading: false,
        reviewItems: [],
        reviewTotal: 0,
        reviewPage: 1,
        reviewStatus: 'PENDING',
        reviewLoading: false,
        reviewDrawer: false,
        reviewDetail: null,
        reviewDetailLoading: false,
        reviewSaving: false,
        reviewForm: { jurisdiction: [], topics: [], applicable_subjects: [] },
        dictOptions: { jurisdiction: [], topic: [], subject: [] },
        todo: {},
        overview: {},
        overviewLoading: false,
        reindexLoading: false,
        dialog: false,
        editing: false,
        editingId: '',
        saving: false,
        form: { category: 'topic', name: '', code: '', enabled: true, sort_order: 0 }
      });

      function loadDict(page) {
        refs.dictPage = page || refs.dictPage;
        refs.dictLoading = true;
        global.api.admin.dictList({ category: refs.dictCategory, page: refs.dictPage, page_size: 20 })
          .then(function (data) {
            refs.dictItems = data.items || [];
            refs.dictTotal = data.total || 0;
          })
          .catch(function () { refs.dictItems = []; })
          .then(function () { refs.dictLoading = false; });
      }

      function loadReview(page) {
        refs.reviewPage = page || refs.reviewPage;
        refs.reviewLoading = true;
        global.api.admin.reviewQueue({ status: refs.reviewStatus, page: refs.reviewPage, page_size: 20 })
          .then(function (data) {
            refs.reviewItems = data.items || [];
            refs.reviewTotal = data.total || 0;
          })
          .catch(function () { refs.reviewItems = []; })
          .then(function () { refs.reviewLoading = false; });
      }

      function loadOverview() {
        refs.overviewLoading = true;
        global.api.admin.overview()
          .then(function (data) { refs.overview = data; })
          .catch(function () {})
          .then(function () { refs.overviewLoading = false; });
      }

      function loadTodo() {
        global.api.admin.todo()
          .then(function (data) { refs.todo = data || {}; })
          .catch(function () {});
      }

      function loadDictOptions() {
        global.api.admin.options()
          .then(function (data) {
            refs.dictOptions.jurisdiction = data.jurisdiction || [];
            refs.dictOptions.topic = data.topic || [];
            refs.dictOptions.subject = data.subject || [];
          })
          .catch(function () {});
      }

      function goTodo(kind) {
        if (kind === 'review') {
          refs.activeTab = 'review';
          loadReview(1);
        } else if (kind === 'crawl') {
          // 采集失败 → 采集台账按失败状态筛选
          global.appRouter.go('crawl', { status: 'FAILED' });
        } else if (kind === 'parse') {
          // 解析失败 → 文件管理按入库状态筛选
          global.appRouter.go('manage', { status: 'FAILED' });
        }
      }

      function openReview(item) {
        refs.reviewDrawer = true;
        refs.reviewDetailLoading = true;
        refs.reviewDetail = null;
        refs.reviewForm = { jurisdiction: [], topics: [], applicable_subjects: [] };
        global.api.admin.reviewDetail(item.id)
          .then(function (data) {
            refs.reviewDetail = data;
            var target = (data.target_type === 'BLOCK' && data.blocks.length)
              ? data.blocks[0]
              : data.document;
            if (target) {
              refs.reviewForm = {
                jurisdiction: (target.jurisdiction || []).slice(),
                topics: (target.topics || []).slice(),
                applicable_subjects: (target.applicable_subjects || []).slice()
              };
            }
          })
          .catch(function () { refs.reviewDetail = null; })
          .then(function () { refs.reviewDetailLoading = false; });
      }

      function submitReview(status) {
        if (!refs.reviewDetail) return;
        refs.reviewSaving = true;
        global.api.admin.handleReview(refs.reviewDetail.id, {
          status: status,
          operator: 'web',
          jurisdiction: refs.reviewForm.jurisdiction,
          topics: refs.reviewForm.topics,
          applicable_subjects: refs.reviewForm.applicable_subjects
        }).then(function () {
          global.ElMessage.success(status === 'APPROVED' ? '已通过并保存修正' : '已驳回');
          refs.reviewDrawer = false;
          loadReview(refs.reviewPage);
          loadTodo();
        }).catch(function () {}).then(function () { refs.reviewSaving = false; });
      }

      function approveWithPatch() { submitReview('APPROVED'); }
      function rejectReview() {
        global.ElMessageBox.confirm('确认驳回该复核项？驳回不会修改标签。', '驳回确认', { type: 'warning' })
          .then(function () { submitReview('REJECTED'); })
          .catch(function () {});
      }

      function reindex() {
        refs.reindexLoading = true;
        global.api.admin.reindex()
          .then(function (data) {
            global.ElMessage.success('索引重建完成：' + data.block_count + ' 个知识块');
            loadOverview();
          })
          .catch(function () {})
          .then(function () { refs.reindexLoading = false; });
      }

      function openCreate() {
        refs.editing = false;
        refs.form = { category: 'topic', name: '', code: '', enabled: true, sort_order: 0 };
        refs.dialog = true;
      }

      function edit(row) {
        refs.editing = true;
        refs.editingId = row.id;
        refs.form = {
          category: row.category,
          name: row.name,
          code: row.code,
          enabled: row.enabled,
          sort_order: row.sort_order
        };
        refs.dialog = true;
      }

      function submit() {
        if (!refs.form.name.trim()) {
          global.ElMessage.warning('请填写名称');
          return;
        }
        refs.saving = true;
        var request = refs.editing
          ? global.api.admin.updateDict(refs.editingId, refs.form)
          : global.api.admin.createDict(refs.form);
        request.then(function () {
          global.ElMessage.success('已保存');
          refs.dialog = false;
          loadDict(refs.dictPage);
        }).catch(function () {}).then(function () { refs.saving = false; });
      }

      function toggle(row) {
        global.api.admin.updateDict(row.id, {
          category: row.category,
          name: row.name,
          code: row.code,
          enabled: !row.enabled,
          sort_order: row.sort_order
        }).then(function () {
          global.ElMessage.success(row.enabled ? '已停用' : '已启用');
          loadDict(refs.dictPage);
        }).catch(function () {});
      }

      function remove(row) {
        global.ElMessageBox.confirm('确认删除字典项「' + row.name + '」？', '删除确认', { type: 'warning' })
          .then(function () { return global.api.admin.removeDict(row.id); })
          .then(function () {
            global.ElMessage.success('已删除');
            loadDict(refs.dictPage);
          })
          .catch(function () {});
      }

      function handle(item, status) {
        global.api.admin.handleReview(item.id, { status: status, operator: 'web' })
          .then(function () {
            global.ElMessage.success('已处理');
            loadReview(refs.reviewPage);
          })
          .catch(function () {});
      }

      Vue.onMounted(function () {
        loadDict(1);
        loadReview(1);
        loadOverview();
        loadTodo();
        loadDictOptions();
      });

      return {
        activeTab: Vue.computed({
          get: function () { return refs.activeTab; },
          set: function (value) { refs.activeTab = value; }
        }),
        categories: Vue.computed(function () { return refs.categories; }),
        dictItems: Vue.computed(function () { return refs.dictItems; }),
        dictTotal: Vue.computed(function () { return refs.dictTotal; }),
        dictPage: Vue.computed(function () { return refs.dictPage; }),
        dictCategory: Vue.computed({
          get: function () { return refs.dictCategory; },
          set: function (value) { refs.dictCategory = value; }
        }),
        dictLoading: Vue.computed(function () { return refs.dictLoading; }),
        reviewItems: Vue.computed(function () { return refs.reviewItems; }),
        reviewTotal: Vue.computed(function () { return refs.reviewTotal; }),
        reviewPage: Vue.computed(function () { return refs.reviewPage; }),
        reviewStatus: Vue.computed({
          get: function () { return refs.reviewStatus; },
          set: function (value) { refs.reviewStatus = value; }
        }),
        reviewLoading: Vue.computed(function () { return refs.reviewLoading; }),
        reviewDrawer: Vue.computed({
          get: function () { return refs.reviewDrawer; },
          set: function (value) { refs.reviewDrawer = value; }
        }),
        reviewDetail: Vue.computed(function () { return refs.reviewDetail; }),
        reviewDetailLoading: Vue.computed(function () { return refs.reviewDetailLoading; }),
        reviewSaving: Vue.computed(function () { return refs.reviewSaving; }),
        reviewForm: Vue.computed(function () { return refs.reviewForm; }),
        dictOptions: Vue.computed(function () { return refs.dictOptions; }),
        todo: Vue.computed(function () { return refs.todo; }),
        drawerSize: Vue.computed(function () {
          return global.innerWidth <= 768 ? '100%' : '68%';
        }),
        reviewStatusClass: global.utils.reviewStatusClass,
        reviewStatusName: function (value) { return global.utils.nameOf(global.utils.REVIEW_STATUS_NAMES, value); },
        overview: Vue.computed(function () { return refs.overview; }),
        overviewLoading: Vue.computed(function () { return refs.overviewLoading; }),
        reindexLoading: Vue.computed(function () { return refs.reindexLoading; }),
        dialog: Vue.computed({
          get: function () { return refs.dialog; },
          set: function (value) { refs.dialog = value; }
        }),
        editing: Vue.computed(function () { return refs.editing; }),
        form: Vue.computed(function () { return refs.form; }),
        saving: Vue.computed(function () { return refs.saving; }),
        loadDict: loadDict,
        loadReview: loadReview,
        loadOverview: loadOverview,
        loadTodo: loadTodo,
        goTodo: goTodo,
        openReview: openReview,
        approveWithPatch: approveWithPatch,
        rejectReview: rejectReview,
        reindex: reindex,
        openCreate: openCreate,
        edit: edit,
        submit: submit,
        toggle: toggle,
        remove: remove,
        handle: handle,
        openTarget: function (item) {
          if (item.target_type === 'DOCUMENT') {
            global.appRouter.go('documents', { id: item.target_id });
          } else {
            global.appRouter.go('documents', { tab: 'search', block: item.target_id });
          }
        }
      };
    }
  };

  global.views = global.views || {};
  global.views.admin = AdminView;
})(window);
