/* ============================================================
   登录页：账号登录，成功后向外壳抛出 logged-in（携带 user 与 token）
   ============================================================ */
(function (global) {
  'use strict';

  var LoginView = {
    template: [
      '<div class="login-wrap">',
      '  <div class="login-card">',
      '    <div class="login-brand">政策知识库</div>',
      '    <div class="login-sub">政策知识库智能应用 · 请登录后使用</div>',
      '    <el-form label-position="top" @submit.prevent="submit">',
      '      <el-form-item label="用户名">',
      '        <el-input v-model="username" placeholder="请输入用户名" @keyup.enter="submit" />',
      '      </el-form-item>',
      '      <el-form-item label="密码">',
      '        <el-input v-model="password" type="password" show-password',
      '          placeholder="请输入密码" @keyup.enter="submit" />',
      '      </el-form-item>',
      '    </el-form>',
      '    <div v-if="error" class="login-error">{{ error }}</div>',
      '    <el-button type="primary" style="width:100%" :loading="loading" @click="submit">登 录</el-button>',
      '    <div class="login-tip">',
      '      <div>演示账号：管理员 <b>admin / admin123</b>　·　普通用户 <b>user / user123</b></div>',
      '      <div style="margin-top:6px">管理员可见「管理后台」，可对政策法规进行新增、编辑、删除。</div>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join(''),

    emits: ['logged-in'],

    setup: function (props, context) {
      var Vue = global.Vue;
      var refs = Vue.reactive({ username: '', password: '', loading: false, error: '' });

      function notify(message, type) {
        try {
          if (global.ElMessage && global.ElMessage[type]) {
            global.ElMessage[type](message);
          }
        } catch (e) {
          /* 提示组件异常不能阻断登录流程 */
        }
      }

      function submit() {
        refs.error = '';
        if (!refs.username.trim() || !refs.password) {
          refs.error = '请输入用户名和密码';
          notify('请输入用户名和密码', 'warning');
          return;
        }
        refs.loading = true;
        global.api.auth
          .login({ username: refs.username.trim(), password: refs.password })
          .then(function (data) {
            // 先抛出登录事件完成跳转，再给提示，避免提示环节异常阻断进入系统
            context.emit('logged-in', { user: data && data.user, token: data && data.token });
            notify('登录成功', 'success');
          })
          .catch(function (error) {
            refs.error = (error && error.message) || '登录失败，请确认后端服务已启动';
          })
          .then(function () {
            refs.loading = false;
          });
      }

      return {
        username: Vue.computed({
          get: function () { return refs.username; },
          set: function (value) { refs.username = value; }
        }),
        password: Vue.computed({
          get: function () { return refs.password; },
          set: function (value) { refs.password = value; }
        }),
        error: Vue.computed(function () { return refs.error; }),
        loading: Vue.computed(function () { return refs.loading; }),
        submit: submit
      };
    }
  };

  global.views = global.views || {};
  global.views.login = LoginView;
})(window);
