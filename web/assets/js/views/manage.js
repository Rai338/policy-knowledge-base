/* ============================================================
   管理后台：政策法规增删改查与导入（管理员）
   - 列表：按文件大类（政策文件/法规）、位阶、时效筛选，一目了然
   - 新增：粘贴正文自动解析切块入库；也支持上传 PDF/DOCX/TXT/MD/HTML
   - 编辑：修改元信息（大类/位阶/时效/文号等），保存后自动重建索引
   - 删除：连带知识块与索引
   说明：导入类写操作已统一收敛到本页，用户端「政策法规库」仅提供检索与浏览。
   ============================================================ */
(function (global) {
  'use strict';

  function emptyForm() {
    return {
      id: '',
      title: '',
      text: '',
      doc_category: 'POLICY',
      effect_level: '',
      document_number: '',
      validity_status: '',
      publish_date: '',
      effective_date: '',
      expiry_date: '',
      source_url: ''
    };
  }

  var ManageView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">政策法规管理</div>',
      '      <div class="text-caption">管理端：对「政策文件」与「法规」进行新增、编辑、删除，保存后自动重建索引</div>',
      '    </div>',
      '    <div class="toolbar">',
      '      <el-input v-model="filters.keyword" class="grow" placeholder="标题或文号关键词" clearable @keyup.enter="load(1)" />',
      '      <el-select v-model="filters.doc_category" clearable placeholder="文件大类" style="width:150px" @change="load(1)">',
      '        <el-option v-for="item in options.doc_categories" :key="item.code" :label="item.name" :value="item.code" />',
      '      </el-select>',
      '      <el-select v-model="filters.effect_level" clearable placeholder="效力位阶" style="width:170px" @change="load(1)">',
      '        <el-option v-for="item in options.effect_levels" :key="item.code" :label="item.name" :value="item.code" />',
      '      </el-select>',
      '      <el-select v-model="filters.validity_status" clearable placeholder="时效状态" style="width:150px" @change="load(1)">',
      '        <el-option v-for="(name, code) in options.validity_status" :key="code" :label="name" :value="code" />',
      '      </el-select>',
      '      <el-select v-model="filters.status" clearable placeholder="入库状态" style="width:140px" @change="load(1)">',
      '        <el-option v-for="(name, code) in docStatusNames" :key="code" :label="name" :value="code" />',
      '      </el-select>',
      '      <el-button type="primary" :loading="loading" @click="load(1)">查询</el-button>',
      '      <el-button type="success" @click="openCreate">新增政策/法规</el-button>',
      '    </div>',
      '    <div class="toolbar">',
      '      <el-upload :http-request="uploadFile" :show-file-list="false" accept=".pdf,.docx,.txt,.md,.html"',
      '        style="display:inline-block">',
      '        <el-button :loading="uploading">上传政策文件</el-button>',
      '      </el-upload>',
      '      <el-button @click="importSamples" :loading="sampleLoading">导入示例政策</el-button>',
      '      <span class="text-caption">支持 PDF / DOCX / TXT / MD / HTML，导入后自动切分为条/款知识块</span>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header">',
      '      <div class="h2">文件列表</div>',
      '      <div class="text-caption">共 {{ total }} 份</div>',
      '    </div>',
      '    <el-table :data="items" size="small" border style="width:100%">',
      '      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />',
      '      <el-table-column label="文件大类" width="100">',
      '        <template #default="s"><b>{{ s.row.doc_category_name }}</b></template>',
      '      </el-table-column>',
      '      <el-table-column prop="effect_level_name" label="效力位阶" width="105" />',
      '      <el-table-column label="时效" width="90">',
      '        <template #default="s">{{ s.row.validity_status_name }}</template>',
      '      </el-table-column>',
      '      <el-table-column label="入库状态" width="100">',
      '        <template #default="s">',
      '          <span class="tag-chip" :class="s.row.status === \'FAILED\' ? \'red\' : (s.row.status === \'INDEXED\' ? \'green\' : \'gray\')">{{ statusName(s.row.status) }}</span>',
      '        </template>',
      '      </el-table-column>',
      '      <el-table-column prop="document_number" label="文号" width="150" show-overflow-tooltip />',
      '      <el-table-column prop="block_count" label="知识块" width="80" align="center" />',
      '      <el-table-column prop="updated_at" label="更新时间" width="150" />',
      '      <el-table-column label="操作" width="130" fixed="right">',
      '        <template #default="s">',
      '          <el-button size="small" @click="openEdit(s.row)">编辑</el-button>',
      '          <el-button size="small" type="danger" @click="remove(s.row)">删除</el-button>',
      '        </template>',
      '      </el-table-column>',
      '    </el-table>',
      '    <div class="toolbar" style="justify-content:flex-end">',
      '      <el-pagination background layout="prev, pager, next" :total="total" :current-page="page"',
      '        :page-size="pageSize" @current-change="load" />',
      '    </div>',
      '  </div>',
      '',
      '  <el-dialog :title="dialogTitle" v-model="dialogVisible" width="700px">',
      '    <el-form :model="form" label-width="110px">',
      '      <el-form-item label="标题" required>',
      '        <el-input v-model="form.title" placeholder="如：芜湖市加快未来产业发展行动方案" />',
      '      </el-form-item>',
      '      <el-form-item label="文件大类" required>',
      '        <el-radio-group v-model="form.doc_category">',
      '          <el-radio v-for="item in options.doc_categories" :key="item.code" :label="item.code">',
      '            {{ item.name }}',
      '          </el-radio>',
      '        </el-radio-group>',
      '      </el-form-item>',
      '      <el-form-item label="效力位阶">',
      '        <el-select v-model="form.effect_level" clearable style="width:100%"',
      '          placeholder="留空则按正文自动判定">',
      '          <el-option v-for="item in options.effect_levels" :key="item.code" :label="item.name" :value="item.code" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="正文" :required="isCreate" v-if="isCreate">',
      '        <el-input v-model="form.text" type="textarea" :rows="8"',
      '          placeholder="粘贴政策/法规正文（保留“第X条”等编号，便于按条切分为知识块）" />',
      '      </el-form-item>',
      '      <el-form-item label="重切块正文" v-else>',
      '        <el-input v-model="form.text" type="textarea" :rows="6"',
      '          placeholder="如需修改正文，请粘贴新正文（保留“第X条”编号）；留空则仅更新元信息，不重新切块" />',
      '      </el-form-item>',
      '      <el-form-item label="文号">',
      '        <el-input v-model="form.document_number" placeholder="如：芜政办〔2025〕5号" />',
      '      </el-form-item>',
      '      <el-form-item label="时效状态">',
      '        <el-select v-model="form.validity_status" clearable style="width:100%">',
      '          <el-option v-for="(name, code) in options.validity_status" :key="code" :label="name" :value="code" />',
      '        </el-select>',
      '      </el-form-item>',
      '      <el-form-item label="印发日期">',
      '        <el-input v-model="form.publish_date" placeholder="如：2025-03-20" />',
      '      </el-form-item>',
      '      <el-form-item label="施行日期">',
      '        <el-input v-model="form.effective_date" placeholder="如：2025-03-20" />',
      '      </el-form-item>',
      '      <el-form-item label="有效期至">',
      '        <el-input v-model="form.expiry_date" placeholder="留空表示长期有效" />',
      '      </el-form-item>',
      '      <el-form-item label="信息来源">',
      '        <el-input v-model="form.source_url" placeholder="原文链接，便于溯源" />',
      '      </el-form-item>',
      '    </el-form>',
      '    <template #footer>',
      '      <el-button @click="dialogVisible = false">取消</el-button>',
      '      <el-button type="primary" :loading="saving" @click="save">保存</el-button>',
      '    </template>',
      '  </el-dialog>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        items: [],
        total: 0,
        page: 1,
        pageSize: 10,
        loading: false,
        saving: false,
        uploading: false,
        sampleLoading: false,
        filters: { keyword: '', doc_category: '', effect_level: '', validity_status: '', status: '' },
        options: { doc_categories: [], effect_levels: [], validity_status: {} },
        docStatusNames: global.utils.DOC_STATUS_NAMES,
        dialogVisible: false,
        isCreate: true,
        dialogTitle: '新增政策/法规',
        form: emptyForm()
      });

      function loadOptions() {
        return global.api.meta
          .options()
          .then(function (data) {
            refs.options.doc_categories = data.doc_categories || [];
            refs.options.effect_levels = data.effect_levels || [];
            refs.options.validity_status = data.validity_status || {};
          })
          .catch(function () {});
      }

      function load(page) {
        refs.page = page || refs.page;
        refs.loading = true;
        global.api.admin
          .docList(Object.assign({}, refs.filters, { page: refs.page, page_size: refs.pageSize }))
          .then(function (data) {
            refs.items = data.items || [];
            refs.total = data.total || 0;
          })
          .catch(function () {
            refs.items = [];
            refs.total = 0;
          })
          .then(function () {
            refs.loading = false;
          });
      }

      function uploadFile(options) {
        var formData = new FormData();
        formData.append('file', options.file);
        refs.uploading = true;
        global.api.documents
          .upload(formData)
          .then(function (data) {
            global.ElMessage.success('导入成功：' + (data.title || ''));
            load(1);
          })
          .catch(function () { /* 接口层已提示 */ })
          .then(function () { refs.uploading = false; });
      }

      function importSamples() {
        refs.sampleLoading = true;
        global.api.documents
          .importSamples()
          .then(function () {
            global.ElMessage.success('示例政策已导入');
            load(1);
          })
          .catch(function () { /* 接口层已提示 */ })
          .then(function () { refs.sampleLoading = false; });
      }

      function openCreate() {
        refs.isCreate = true;
        refs.dialogTitle = '新增政策/法规';
        refs.form = emptyForm();
        refs.dialogVisible = true;
      }

      function openEdit(row) {
        refs.isCreate = false;
        refs.dialogTitle = '编辑：' + row.title;
        refs.form = {
          id: row.id,
          title: row.title,
          text: '',
          doc_category: row.doc_category || 'POLICY',
          effect_level: row.effect_level || '',
          document_number: row.document_number || '',
          validity_status: row.validity_status || '',
          publish_date: row.publish_date || '',
          effective_date: row.effective_date || '',
          expiry_date: row.expiry_date || '',
          source_url: row.source_url || ''
        };
        refs.dialogVisible = true;
      }

      function save() {
        if (!refs.form.title.trim()) {
          global.ElMessage.warning('请填写标题');
          return;
        }
        if (refs.isCreate && !refs.form.text.trim()) {
          global.ElMessage.warning('新增时请粘贴正文');
          return;
        }
        refs.saving = true;
        var body = {
          title: refs.form.title,
          text: refs.form.text,
          doc_category: refs.form.doc_category,
          effect_level: refs.form.effect_level,
          document_number: refs.form.document_number,
          validity_status: refs.form.validity_status,
          publish_date: refs.form.publish_date,
          effective_date: refs.form.effective_date,
          expiry_date: refs.form.expiry_date,
          source_url: refs.form.source_url
        };
        var request = refs.isCreate
          ? global.api.admin.createDoc(body)
          : global.api.admin.updateDoc(refs.form.id, body);
        request
          .then(function () {
            global.ElMessage.success('保存成功');
            refs.dialogVisible = false;
            load(refs.page);
          })
          .catch(function () { /* 接口层已提示 */ })
          .then(function () {
            refs.saving = false;
          });
      }

      function remove(row) {
        global.ElMessageBox.confirm(
          '确定删除《' + row.title + '》？该操作会连带删除其知识块与索引，且不可恢复。',
          '删除确认',
          { type: 'warning' }
        )
          .then(function () {
            return global.api.admin.removeDoc(row.id);
          })
          .then(function () {
            global.ElMessage.success('已删除');
            load(refs.page);
          })
          .catch(function () { /* 取消或失败 */ });
      }

      Vue.onMounted(function () {
        // 支持从管理员待办概览直达：?status=FAILED 时预置"解析失败"筛选
        var presetStatus = global.appRouter.getQuery('status');
        if (presetStatus) {
          refs.filters.status = presetStatus;
        }
        loadOptions().then(function () {
          load(1);
        });
      });

      return {
        items: Vue.computed(function () { return refs.items; }),
        total: Vue.computed(function () { return refs.total; }),
        page: Vue.computed(function () { return refs.page; }),
        pageSize: Vue.computed(function () { return refs.pageSize; }),
        loading: Vue.computed(function () { return refs.loading; }),
        saving: Vue.computed(function () { return refs.saving; }),
        uploading: Vue.computed(function () { return refs.uploading; }),
        sampleLoading: Vue.computed(function () { return refs.sampleLoading; }),
        filters: refs.filters,
        options: refs.options,
        docStatusNames: Vue.computed(function () { return refs.docStatusNames; }),
        statusName: function (value) { return global.utils.nameOf(global.utils.DOC_STATUS_NAMES, value); },
        form: Vue.computed({
          get: function () { return refs.form; },
          set: function (value) { refs.form = value; }
        }),
        isCreate: Vue.computed(function () { return refs.isCreate; }),
        dialogTitle: Vue.computed(function () { return refs.dialogTitle; }),
        dialogVisible: Vue.computed({
          get: function () { return refs.dialogVisible; },
          set: function (value) { refs.dialogVisible = value; }
        }),
        load: load,
        uploadFile: uploadFile,
        importSamples: importSamples,
        openCreate: openCreate,
        openEdit: openEdit,
        save: save,
        remove: remove
      };
    }
  };

  global.views = global.views || {};
  global.views.manage = ManageView;
})(window);
