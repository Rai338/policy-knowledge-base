/* ============================================================
   账号管理（ADM-USER）：用户列表 / 新增 / 启停 / 改密 / 删除（管理员）
   与后端本地 User 模型（role + status + password_hash）对齐：
   角色 USER/ADMIN，状态 ACTIVE/DISABLED。
   ============================================================ */
(function (global) {
  'use strict';

  function emptyForm() {
    return {
      id: '',
      username: '',
      display_name: '',
      role: 'USER',
      status: 'ACTIVE',
      password: ''
    };
  }

  var UsersView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">账号管理</div>',
      '      <div class="text-caption">后台账号的增删改与启停（仅管理员可见）</div>',
      '    </div>',
      '    <div class="toolbar">',
      '      <el-input v-model="filters.keyword" class="grow" placeholder="用户名 / 显示名关键词" clearable @keyup.enter="load" />',
      '      <el-select v-model="filters.role" clearable placeholder="角色" style="width:140px" @change="applyFilters">',
      '        <el-option label="管理员" value="ADMIN" />',
      '        <el-option label="普通用户" value="USER" />',
      '      </el-select>',
      '      <el-select v-model="filters.status" clearable placeholder="状态" style="width:140px" @change="applyFilters">',
      '        <el-option label="正常" value="ACTIVE" />',
      '        <el-option label="已停用" value="DISABLED" />',
      '      </el-select>',
      '      <el-button :loading="loading" @click="load">查询</el-button>',
      '      <el-button type="success" @click="openCreate">新增账号</el-button>',
      '    </div>',
      '  </div>',
      '',
      '  <div class="card" v-loading="loading">',
      '    <div class="card-header"><div class="h2">账号列表</div><div class="text-caption">共 {{ total }} 个</div></div>',
      '    <el-table :data="items" size="small" border style="width:100%">',
      '      <el-table-column prop="username" label="用户名" width="160" />',
      '      <el-table-column prop="display_name" label="显示名" min-width="120" />',
      '      <el-table-column label="角色" width="110">',
      '        <template #default="s"><span class="tag-chip" :class="s.row.role === \'ADMIN\' ? \'\' : \'gray\'">{{ s.row.role_name }}</span></template>',
      '      </el-table-column>',
      '      <el-table-column label="状态" width="100">',
      '        <template #default="s"><span class="tag-chip" :class="s.row.status === \'ACTIVE\' ? \'green\' : \'red\'">{{ s.row.status_name }}</span></template>',
      '      </el-table-column>',
      '      <el-table-column prop="last_login_at" label="最后登录" width="170" />',
      '      <el-table-column prop="created_at" label="创建时间" width="170" />',
      '      <el-table-column label="操作" width="230" fixed="right">',
      '        <template #default="s">',
      '          <el-button size="small" @click="openEdit(s.row)">编辑</el-button>',
      '          <el-button size="small" v-if="s.row.status === \'ACTIVE\'" @click="toggleStatus(s.row, \'DISABLED\')">停用</el-button>',
      '          <el-button size="small" v-else @click="toggleStatus(s.row, \'ACTIVE\')">启用</el-button>',
      '          <el-button size="small" type="danger" :disabled="s.row.id === currentUserId" @click="remove(s.row)">删除</el-button>',
      '        </template>',
      '      </el-table-column>',
      '    </el-table>',
      '  </div>',
      '',
      '  <el-dialog :title="dialogTitle" v-model="dialogVisible" width="460px">',
      '    <el-form :model="form" label-width="88px">',
      '      <el-form-item label="用户名" v-if="isCreate" required>',
      '        <el-input v-model="form.username" placeholder="登录用户名（唯一）" />',
      '      </el-form-item>',
      '      <el-form-item label="显示名">',
      '        <el-input v-model="form.display_name" placeholder="默认与用户名相同" />',
      '      </el-form-item>',
      '      <el-form-item label="角色">',
      '        <el-radio-group v-model="form.role">',
      '          <el-radio label="USER">普通用户</el-radio>',
      '          <el-radio label="ADMIN">管理员</el-radio>',
      '        </el-radio-group>',
      '      </el-form-item>',
      '      <el-form-item label="状态" v-if="!isCreate">',
      '        <el-radio-group v-model="form.status">',
      '          <el-radio label="ACTIVE">正常</el-radio>',
      '          <el-radio label="DISABLED">已停用</el-radio>',
      '        </el-radio-group>',
      '      </el-form-item>',
      '      <el-form-item :label="isCreate ? \'初始密码\' : \'新密码\'" :required="isCreate">',
      '        <el-input v-model="form.password" type="password" show-password',
      '          :placeholder="isCreate ? \'至少 6 位\' : \'留空则不修改\'" />',
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
        all: [],
        items: [],
        total: 0,
        loading: false,
        saving: false,
        filters: { keyword: '', role: '', status: '' },
        dialogVisible: false,
        isCreate: true,
        dialogTitle: '新增账号',
        form: emptyForm()
      });

      function load() {
        refs.loading = true;
        global.api.admin.users.list()
          .then(function (data) {
            refs.all = Array.isArray(data) ? data : (data.items || []);
            applyFilters();
          })
          .catch(function () { refs.all = []; refs.items = []; refs.total = 0; })
          .then(function () { refs.loading = false; });
      }

      function applyFilters() {
        var kw = (refs.filters.keyword || '').trim().toLowerCase();
        refs.items = refs.all.filter(function (u) {
          if (refs.filters.role && u.role !== refs.filters.role) return false;
          if (refs.filters.status && u.status !== refs.filters.status) return false;
          if (kw && (u.username + (u.display_name || '')).toLowerCase().indexOf(kw) < 0) return false;
          return true;
        });
        refs.total = refs.items.length;
      }

      function openCreate() {
        refs.isCreate = true;
        refs.dialogTitle = '新增账号';
        refs.form = emptyForm();
        refs.dialogVisible = true;
      }

      function openEdit(row) {
        refs.isCreate = false;
        refs.dialogTitle = '编辑：' + row.username;
        refs.form = {
          id: row.id,
          username: row.username,
          display_name: row.display_name || '',
          role: row.role || 'USER',
          status: row.status || 'ACTIVE',
          password: ''
        };
        refs.dialogVisible = true;
      }

      function save() {
        if (refs.isCreate) {
          if (!refs.form.username.trim()) {
            global.ElMessage.warning('请填写用户名');
            return;
          }
          if (!refs.form.password) {
            global.ElMessage.warning('请设置初始密码');
            return;
          }
        }
        if (refs.form.password && refs.form.password.length < 6) {
          global.ElMessage.warning('密码至少 6 位');
          return;
        }
        refs.saving = true;
        var body;
        if (refs.isCreate) {
          body = {
            username: refs.form.username.trim(),
            display_name: refs.form.display_name.trim(),
            role: refs.form.role,
            password: refs.form.password
          };
        } else {
          body = {
            display_name: refs.form.display_name.trim(),
            role: refs.form.role,
            status: refs.form.status,
            password: refs.form.password
          };
        }
        var request = refs.isCreate
          ? global.api.admin.users.create(body)
          : global.api.admin.users.update(refs.form.id, body);
        request
          .then(function () {
            global.ElMessage.success('保存成功');
            refs.dialogVisible = false;
            load();
          })
          .catch(function () { /* 接口层已提示 */ })
          .then(function () { refs.saving = false; });
      }

      function toggleStatus(row, status) {
        var label = status === 'DISABLED' ? '停用' : '启用';
        global.ElMessageBox.confirm('确定' + label + '账号「' + row.username + '」？', label, { type: 'warning' })
          .then(function () {
            return global.api.admin.users.update(row.id, { status: status });
          })
          .then(function () {
            global.ElMessage.success(label + '成功');
            load();
          })
          .catch(function () { /* 取消或失败 */ });
      }

      function remove(row) {
        global.ElMessageBox.confirm(
          '确定删除账号「' + row.username + '」？该操作不可恢复。',
          '删除确认', { type: 'warning' }
        )
          .then(function () { return global.api.admin.users.remove(row.id); })
          .then(function () {
            global.ElMessage.success('已删除');
            load();
          })
          .catch(function () { /* 取消或失败 */ });
      }

      Vue.onMounted(function () { load(); });

      return {
        items: Vue.computed(function () { return refs.items; }),
        total: Vue.computed(function () { return refs.total; }),
        loading: Vue.computed(function () { return refs.loading; }),
        saving: Vue.computed(function () { return refs.saving; }),
        filters: refs.filters,
        dialogVisible: Vue.computed({
          get: function () { return refs.dialogVisible; },
          set: function (value) { refs.dialogVisible = value; }
        }),
        isCreate: Vue.computed(function () { return refs.isCreate; }),
        dialogTitle: Vue.computed(function () { return refs.dialogTitle; }),
        form: Vue.computed({
          get: function () { return refs.form; },
          set: function (value) { refs.form = value; }
        }),
        currentUserId: Vue.computed(function () {
          return (global.appAuth && global.appAuth.state && global.appAuth.state.user)
            ? global.appAuth.state.user.id : '';
        }),
        load: load,
        applyFilters: applyFilters,
        openCreate: openCreate,
        openEdit: openEdit,
        save: save,
        toggleStatus: toggleStatus,
        remove: remove
      };
    }
  };

  global.views = global.views || {};
  global.views.users = UsersView;
})(window);
