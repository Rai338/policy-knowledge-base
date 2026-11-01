/* ============================================================
   政策法规库（用户端统一入口）
   - 条款检索：语义 + 关键词混合检索，命中到条/款，可查看原文与上下文
   - 文件浏览：按大类/位阶/时效浏览文件，查看详情与知识块
   说明：原「政策检索」页与「政策问答」页已并入此处/AI 对话，
        导入、删除等写操作集中在管理端「政策法规管理」。
   ============================================================ */
(function (global) {
  'use strict';

  var DocumentsView = {
    template: [
      '<div>',
      '  <div class="card">',
      '    <div class="card-header">',
      '      <div class="h1">政策搜索</div>',
      '      <div class="text-caption">条款检索（RAG 语义 + 关键词）与文件浏览，结果可溯源到原文条款</div>',
      '    </div>',
      '    <el-tabs v-model="tab" @tab-change="onTabChange">',
      '',
      '      <el-tab-pane label="条款检索" name="search">',
      '        <div class="toolbar">',
      '          <el-input v-model="keyword" class="grow" placeholder="输入政策关键词，如：高新技术企业 奖励"',
      '            clearable @keyup.enter="doSearch(1)" @clear="resetSearch" />',
      '          <el-button type="primary" :loading="searching" @click="doSearch(1)">检索</el-button>',
      '        </div>',
      '        <div class="toolbar">',
      '          <el-select v-model="filters.doc_categories" multiple collapse-tags clearable',
      '            placeholder="文件大类" style="width:170px">',
      '            <el-option v-for="item in options.doc_categories" :key="item.code" :label="item.name" :value="item.code" />',
      '          </el-select>',
      '          <el-select v-model="filters.effect_levels" multiple collapse-tags collapse-tags-tooltip clearable',
      '            placeholder="效力位阶" style="width:200px">',
      '            <el-option v-for="item in options.effect_levels" :key="item.code" :label="item.name" :value="item.code" />',
      '          </el-select>',
      '          <el-select v-model="filters.validity_statuses" multiple collapse-tags clearable',
      '            placeholder="时效状态" style="width:180px">',
      '            <el-option v-for="(name, code) in options.validity_status" :key="code" :label="name" :value="code" />',
      '          </el-select>',
      '          <el-select v-model="sortBy" placeholder="排序" style="width:150px">',
      '            <el-option label="相关度优先" value="relevance" />',
      '            <el-option label="发布时间优先" value="date" />',
      '            <el-option label="效力位阶优先" value="level" />',
      '          </el-select>',
      '          <el-checkbox v-model="onlyCurrent" style="margin-left:4px">仅现行有效</el-checkbox>',
      '        </div>',
      '        <div v-loading="searching">',
      '          <div v-if="searching && !items.length">',
      '            <el-skeleton :rows="3" animated v-for="n in 3" :key="n" />',
      '          </div>',
      '          <div v-else-if="!items.length" class="empty-state">',
      '            <el-empty :description="emptyTip" />',
      '          </div>',
      '          <div v-else>',
      '            <div class="text-caption" style="margin-bottom:8px">',
      '              共 {{ total }} 条 · 耗时 {{ latency }} ms · 检索方式：RAG 混合召回（语义向量 {{ retrieval.embedding_backend }} + 关键词 BM25）',
      '            </div>',
      '            <div class="notice-bar" v-if="excludedByValidity > 0">',
      '              <span>另有 {{ excludedByValidity }} 条命中来自已失效 / 未生效文件，已被“仅现行有效”过滤，取消勾选可查看。</span>',
      '            </div>',
      '            <div class="result-item" v-for="item in items" :key="item.block_id">',
      '              <div class="result-title" @click="openBlock(item.block_id)" style="cursor:pointer">{{ item.title }}</div>',
      '              <div class="result-meta">',
      '                <span class="tag-chip" style="background:var(--color-primary-bg);color:var(--color-primary);font-weight:600">{{ item.doc_category_name }}</span>',
      '                <span class="tag-chip">{{ item.effect_level_name }}</span>',
      '                <span class="tag-chip" :class="validityClass(item.validity_status)">{{ item.validity_status_name }}</span>',
      '                <span class="tag-chip gray" v-if="item.article_number">{{ item.article_number }}{{ item.clause_number ? " 第" + item.clause_number + "款" : "" }}</span>',
      '                <span class="tag-chip gray" v-if="item.publish_date">{{ item.publish_date }}</span>',
      '                <span class="tag-chip gray" v-if="item.match_type">RAG {{ item.match_type }}</span>',
      '                <span class="text-caption">相关度 {{ item.score.toFixed(3) }} · 语义 {{ (item.semantic_score || 0).toFixed(3) }} · 关键词 {{ (item.keyword_score || 0).toFixed(3) }}</span>',
      '              </div>',
      '              <div class="result-text" v-html="item.highlight"></div>',
      '              <div class="text-caption" style="margin-top:8px">来源：{{ item.document_title }}</div>',
      '              <div class="toolbar" style="margin:8px 0 0">',
      '                <el-button size="small" @click="openBlock(item.block_id)">查看原文与上下文</el-button>',
      '                <el-button size="small" @click="openDocument(item.document_id)">所属文件</el-button>',
      '                <el-button size="small" @click="openRelated(item.block_id)">关联政策</el-button>',
      '              </div>',
      '            </div>',
      '            <el-pagination background layout="total, sizes, prev, pager, next"',
      '              :total="total" :current-page="searchPage" :page-size="searchPageSize"',
      '              :page-sizes="[10, 20, 50]" @current-change="doSearch" @size-change="changeSearchSize"',
      '              style="margin-top:16px" />',
      '          </div>',
      '          <div v-if="web && (web.engine || (web.results && web.results.length))" class="web-block">',
      '            <div class="card-header">',
      '              <div class="h3">联网补充检索</div>',
      '              <div class="text-caption">{{ web.engine ? "引擎：" + web.engine : "未配置联网检索服务" }}</div>',
      '            </div>',
      '            <div class="notice-bar"><span>{{ web.message }}</span></div>',
      '            <div v-if="web.results && web.results.length">',
      '              <div class="result-item" v-for="(r, idx) in web.results" :key="idx">',
      '                <div class="result-title">',
      '                  <a :href="r.url" target="_blank" rel="noopener"',
      '                    style="color:inherit;text-decoration:none">{{ r.title }}</a>',
      '                </div>',
      '                <div class="result-text">{{ r.snippet }}</div>',
      '                <div class="text-caption" style="margin-top:6px">来源：{{ r.source }} · {{ r.url }}</div>',
      '              </div>',
      '            </div>',
      '            <div v-else class="toolbar" style="flex-wrap:wrap">',
      '              <el-button v-for="s in web.suggestions" :key="s.name" size="small" @click="openExternal(s.url)">',
      '                在{{ s.name }}检索',
      '              </el-button>',
      '            </div>',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '',
      '      <el-tab-pane label="文件浏览" name="files">',
      '        <div class="toolbar">',
      '          <el-input v-model="filters.keyword" class="grow" placeholder="标题或文号关键词" clearable @keyup.enter="load(1)" />',
      '          <el-select v-model="filters.doc_category" clearable placeholder="文件大类" style="width:150px" @change="load(1)">',
      '            <el-option v-for="item in options.doc_categories" :key="item.code" :label="item.name" :value="item.code" />',
      '          </el-select>',
      '          <el-select v-model="filters.effect_level" clearable placeholder="效力位阶" style="width:170px" @change="load(1)">',
      '            <el-option v-for="item in options.effect_levels" :key="item.code" :label="item.name" :value="item.code" />',
      '          </el-select>',
      '          <el-select v-model="filters.validity_status" clearable placeholder="时效状态" style="width:150px" @change="load(1)">',
      '            <el-option v-for="(name, code) in options.validity_status" :key="code" :label="name" :value="code" />',
      '          </el-select>',
      '          <el-button type="primary" :loading="loading" @click="load(1)">查询</el-button>',
      '        </div>',
      '        <div v-loading="loading">',
      '          <div v-if="!documents.length" class="empty-state">',
      '            <el-empty description="暂无政策文件，可由管理员在「政策法规管理」中导入" />',
      '          </div>',
      '          <div v-else>',
      '            <div class="result-item" v-for="item in documents" :key="item.id">',
      '              <div class="result-title" @click="openDetail(item.id)" style="cursor:pointer">{{ item.title }}</div>',
      '              <div class="result-meta">',
      '                <span class="tag-chip" style="background:var(--color-primary-bg);color:var(--color-primary);font-weight:600">{{ item.doc_category_name }}</span>',
      '                <span class="tag-chip">{{ item.effect_level_name }}</span>',
      '                <span class="tag-chip" :class="validityClass(item.validity_status)">{{ item.validity_status_name }}</span>',
      '                <span class="tag-chip gray">{{ item.source_type === "CRAWL" ? "自动采集" : "人工上传" }}</span>',
      '                <span class="tag-chip gray" v-if="item.document_number">{{ item.document_number }}</span>',
      '                <span class="text-caption">{{ item.publish_date || "发布日期未识别" }} · {{ item.block_count }} 个知识块</span>',
      '              </div>',
      '              <div class="text-secondary">{{ truncate(item.summary, 120) }}</div>',
      '              <div class="toolbar" style="margin:8px 0 0">',
      '                <el-button size="small" @click="openDetail(item.id)">详情与知识块</el-button>',
      '                <el-button size="small" @click="goAnalysis(item.id)">摘要与解读</el-button>',
      '                <el-button size="small" @click="openCompare(item.id)">修订对照</el-button>',
      '              </div>',
      '            </div>',
      '            <el-pagination background layout="total, prev, pager, next" :total="docTotal"',
      '              :current-page="page" :page-size="pageSize" @current-change="load" />',
      '          </div>',
      '        </div>',
      '      </el-tab-pane>',
      '    </el-tabs>',
      '  </div>',
      '',
      '  <el-drawer v-model="detailDrawer" :size="drawerSize" title="文件详情">',
      '    <div v-if="detailLoading"><el-skeleton :rows="5" animated /></div>',
      '    <div v-else-if="detail">',
      '      <div class="h2">{{ detail.document.title }}</div>',
      '      <div class="result-meta" style="margin-top:8px">',
      '        <span class="tag-chip">{{ detail.document.effect_level_name }}</span>',
      '        <span class="tag-chip" :class="validityClass(detail.document.validity_status)">{{ detail.document.validity_status_name }}</span>',
      '        <span class="tag-chip gray" v-if="detail.document.document_number">{{ detail.document.document_number }}</span>',
      '      </div>',
      '      <div class="text-caption" style="margin:8px 0">',
      '        发文机关：{{ (detail.document.issuing_authority || []).join("、") || "未识别" }}',
      '      </div>',
      '      <div class="text-caption">',
      '        发布 {{ detail.document.publish_date || "—" }} · 生效 {{ detail.document.effective_date || "—" }} · 失效 {{ detail.document.expiry_date || "—" }} · 状态 {{ statusName(detail.document.status) }}',
      '      </div>',
      '      <div class="toolbar" style="margin-top:12px">',
      '        <el-button size="small" @click="goAnalysis(detail.document.id)">摘要与解读</el-button>',
      '        <a :href="detail.document.source_url" target="_blank" v-if="detail.document.source_url">',
      '          <el-button size="small">查看来源网页</el-button>',
      '        </a>',
      '      </div>',
      '      <div class="card" style="box-shadow:none;margin-top:12px">',
      '        <div class="h3">版本记录</div>',
      '        <div v-if="!detail.versions.length" class="text-caption">暂无版本记录</div>',
      '        <div v-for="version in detail.versions" :key="version.id" class="block-quote" style="margin-bottom:6px">',
      '          {{ version.version_label }} · {{ version.change_note || "—" }} · {{ version.created_at }}',
      '          <span class="tag-chip green" v-if="version.is_current">当前版本</span>',
      '        </div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none">',
      '        <div class="card-header"><div class="h3">知识块（{{ detail.blocks.total }}）</div></div>',
      '        <div v-if="!detail.blocks.items.length" class="empty-state">该文件暂无知识块</div>',
      '        <div v-for="block in detail.blocks.items" :key="block.block_id" class="block-quote" style="margin-bottom:10px;cursor:pointer"',
      '          @click="openBlock(block.block_id)">',
      '          <div style="font-weight:600">',
      '            {{ block.article_number || "—" }}{{ block.clause_number ? " 第" + block.clause_number + "款" : "" }}',
      '            <span class="tag-chip gray">{{ block.granularity === "CLAUSE" ? "款" : "条" }}</span>',
      '          </div>',
      '          <div>{{ truncate(block.original_text, 160) }}</div>',
      '        </div>',
      '        <el-pagination small background layout="prev, pager, next" :total="detail.blocks.total"',
      '          :current-page="blockPage" :page-size="20" @current-change="changeBlockPage" v-if="detail.blocks.total > 20" />',
      '      </div>',
      '    </div>',
      '    <div v-else class="empty-state">未加载到文件</div>',
      '  </el-drawer>',
      '',
      '  <el-drawer v-model="blockDrawer" :size="drawerSize" title="知识块详情">',
      '    <div v-if="blockLoading"><el-skeleton :rows="4" animated /></div>',
      '    <div v-else-if="blockDetail">',
      '      <div class="h2">{{ blockDetail.block.title }}</div>',
      '      <div class="result-meta" style="margin-top:8px">',
      '        <span class="tag-chip">{{ blockDetail.block.effect_level_name }}</span>',
      '        <span class="tag-chip" :class="validityClass(blockDetail.block.validity_status)">{{ blockDetail.block.validity_status_name }}</span>',
      '        <span class="tag-chip gray">{{ blockDetail.block.granularity === "CLAUSE" ? "款级" : "条级" }}</span>',
      '      </div>',
      '      <div class="text-caption" style="margin:8px 0">',
      '        《{{ blockDetail.document.title }}》{{ blockDetail.document.document_number ? " · " + blockDetail.document.document_number : "" }}',
      '        <span v-if="blockDetail.block.page_start"> · 第 {{ blockDetail.block.page_start }} 页</span>',
      '      </div>',
      '      <div class="card" style="box-shadow:none">',
      '        <div class="h3">原文</div>',
      '        <div style="white-space:pre-wrap;line-height:1.9">{{ blockDetail.block.original_text }}</div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none" v-if="blockDetail.block.context_before">',
      '        <div class="h3">上文</div>',
      '        <div class="block-quote">{{ blockDetail.block.context_before }}</div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none" v-if="blockDetail.block.context_after">',
      '        <div class="h3">下文</div>',
      '        <div class="block-quote">{{ blockDetail.block.context_after }}</div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none" v-if="blockDetail.block.higher_law_refs && blockDetail.block.higher_law_refs.length">',
      '        <div class="h3">上位法引用</div>',
      '        <div><span class="tag-chip" v-for="ref in blockDetail.block.higher_law_refs" :key="ref">{{ ref }}</span></div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none" v-if="blockDetail.children && blockDetail.children.length">',
      '        <div class="h3">款级细分</div>',
      '        <div v-for="child in blockDetail.children" :key="child.block_id" class="block-quote" style="margin-bottom:8px">',
      '          {{ child.clause_number }}：{{ child.original_text }}',
      '        </div>',
      '      </div>',
      '      <div class="card" style="box-shadow:none" v-if="blockDetail.similar && blockDetail.similar.length">',
      '        <div class="h3">相似知识块</div>',
      '        <div v-for="sim in blockDetail.similar" :key="sim.block_id" class="block-quote" style="margin-bottom:8px;cursor:pointer"',
      '          @click="openBlock(sim.block_id)">',
      '          {{ sim.title }}：{{ truncate(sim.original_text, 90) }}',
      '        </div>',
      '      </div>',
      '      <div class="toolbar">',
      '        <el-button size="small" @click="openDocument(blockDetail.block.document_id)">查看所属文件</el-button>',
      '        <el-button size="small" @click="openRelated(blockDetail.block.block_id)">关联政策</el-button>',
      '      </div>',
      '    </div>',
      '    <div v-else class="empty-state">未加载到知识块</div>',
      '  </el-drawer>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        tab: 'search',
        // 条款检索
        keyword: '',
        items: [],
        total: 0,
        searchPage: 1,
        searchPageSize: 10,
        latency: 0,
        searching: false,
        searched: false,
        excludedByValidity: 0,
        retrieval: {},
        web: null,
        region: '',
        sortBy: 'relevance',
        onlyCurrent: true,
        // 文件浏览
        documents: [],
        docTotal: 0,
        page: 1,
        pageSize: 10,
        loading: false,
        filters: {
          keyword: '',
          doc_category: '',
          effect_level: '',
          validity_status: '',
          source_type: '',
          doc_categories: [],
          effect_levels: [],
          validity_statuses: []
        },
        options: {
          doc_categories: [],
          effect_levels: [],
          validity_status: {}
        },
        detailDrawer: false,
        detail: null,
        detailLoading: false,
        blockPage: 1,
        blockDrawer: false,
        blockDetail: null,
        blockLoading: false
      });

      function loadOptions() {
        return global.api.meta.options()
          .then(function (data) {
            refs.options.doc_categories = data.doc_categories || [];
            refs.options.effect_levels = data.effect_levels || [];
            refs.options.validity_status = data.validity_status || {};
          })
          .catch(function () {});
      }

      // ---------------- 条款检索 ----------------
      function doSearch(page) {
        var keyword = refs.keyword.trim();
        if (!keyword) {
          global.ElMessage.warning('请输入检索关键词');
          return;
        }
        refs.searchPage = page || 1;
        refs.searching = true;
        var params = {
          q: keyword,
          page: refs.searchPage,
          page_size: refs.searchPageSize,
          sort_by: refs.sortBy,
          only_current: refs.onlyCurrent,
          region: global.appRegion.state.value
        };
        ['doc_categories', 'effect_levels', 'validity_statuses'].forEach(function (key) {
          if (refs.filters[key] && refs.filters[key].length) params[key] = refs.filters[key];
        });
        global.api.search.query(params)
          .then(function (data) {
            refs.items = data.items || [];
            refs.total = data.total || 0;
            refs.retrieval = data.retrieval || {};
            refs.web = data.web || null;
            refs.latency = data.latency_ms || 0;
            refs.excludedByValidity = data.excluded_by_validity || 0;
            refs.searched = true;
          })
          .catch(function () {
            refs.items = [];
            refs.total = 0;
            refs.searched = true;
          })
          .then(function () { refs.searching = false; });
      }

      function changeSearchSize(size) {
        refs.searchPageSize = size;
        doSearch(1);
      }

      function resetSearch() {
        refs.items = [];
        refs.total = 0;
        refs.searched = false;
        refs.web = null;
      }

      // ---------------- 文件浏览 ----------------
      function load(page) {
        refs.page = page || refs.page;
        refs.loading = true;
        global.api.documents.list({
          keyword: refs.filters.keyword,
          doc_category: refs.filters.doc_category,
          effect_level: refs.filters.effect_level,
          validity_status: refs.filters.validity_status,
          source_type: refs.filters.source_type,
          region: global.appRegion.state.value,
          page: refs.page,
          page_size: refs.pageSize
        }).then(function (data) {
          refs.documents = data.items || [];
          refs.docTotal = data.total || 0;
        }).catch(function () {
          refs.documents = [];
          refs.docTotal = 0;
        }).then(function () { refs.loading = false; });
      }

      function openDetail(documentId, blockPage) {
        refs.detailDrawer = true;
        refs.detailLoading = true;
        refs.detail = null;
        refs.blockPage = blockPage || 1;
        global.api.documents.detail(documentId, { block_page: refs.blockPage, block_page_size: 20 })
          .then(function (data) { refs.detail = data; })
          .catch(function () { refs.detail = null; })
          .then(function () { refs.detailLoading = false; });
      }

      function changeBlockPage(page) {
        if (refs.detail) openDetail(refs.detail.document.id, page);
      }

      function openBlock(blockId) {
        refs.tab = 'search';
        refs.blockDrawer = true;
        refs.blockLoading = true;
        refs.blockDetail = null;
        global.api.search.block(blockId)
          .then(function (data) { refs.blockDetail = data; })
          .catch(function () { refs.blockDetail = null; })
          .then(function () { refs.blockLoading = false; });
      }

      function openDocument(documentId) {
        refs.tab = 'files';
        openDetail(documentId);
      }

      function onTabChange(name) {
        if (name === 'files' && !refs.documents.length && !refs.loading) {
          load(1);
        }
      }

      Vue.onMounted(function () {
        loadOptions().then(function () {
          var tab = global.appRouter.getQuery('tab');
          var preset = global.appRouter.getQuery('q');
          var blockId = global.appRouter.getQuery('block');
          var documentId = global.appRouter.getQuery('id');
          if (tab === 'files') {
            refs.tab = 'files';
            load(1);
          } else {
            refs.tab = 'search';
          }
          if (documentId) {
            openDetail(documentId);
            return;
          }
          if (blockId) {
            openBlock(blockId);
            return;
          }
          if (preset) {
            refs.keyword = preset;
            doSearch(1);
          }
        });
        // 地区切换：刷新当前页数据（检索按关键词重跑，文件浏览重新拉取）
        Vue.watch(function () { return global.appRegion.state.value; }, function () {
          if (refs.tab === 'files') {
            load(1);
          } else if (refs.keyword.trim()) {
            doSearch(refs.searchPage);
          }
        });
      });

      return {
        tab: Vue.computed({
          get: function () { return refs.tab; },
          set: function (value) { refs.tab = value; }
        }),
        keyword: Vue.computed({
          get: function () { return refs.keyword; },
          set: function (value) { refs.keyword = value; }
        }),
        items: Vue.computed(function () { return refs.items; }),
        total: Vue.computed(function () { return refs.total; }),
        searchPage: Vue.computed(function () { return refs.searchPage; }),
        searchPageSize: Vue.computed(function () { return refs.searchPageSize; }),
        latency: Vue.computed(function () { return refs.latency; }),
        searching: Vue.computed(function () { return refs.searching; }),
        searched: Vue.computed(function () { return refs.searched; }),
        excludedByValidity: Vue.computed(function () { return refs.excludedByValidity; }),
        retrieval: Vue.computed(function () { return refs.retrieval; }),
        web: Vue.computed(function () { return refs.web; }),
        emptyTip: Vue.computed(function () {
          if (!refs.searched) return '输入关键词，检索政策与法规条款';
          if (refs.excludedByValidity > 0) {
            return '有 ' + refs.excludedByValidity + ' 条命中但均为已失效 / 未生效文件，取消“仅现行有效”可查看';
          }
          return '未检索到相关政策，请调整关键词或筛选条件';
        }),
        sortBy: Vue.computed({
          get: function () { return refs.sortBy; },
          set: function (value) { refs.sortBy = value; }
        }),
        onlyCurrent: Vue.computed({
          get: function () { return refs.onlyCurrent; },
          set: function (value) { refs.onlyCurrent = value; }
        }),
        documents: Vue.computed(function () { return refs.documents; }),
        docTotal: Vue.computed(function () { return refs.docTotal; }),
        page: Vue.computed(function () { return refs.page; }),
        pageSize: Vue.computed(function () { return refs.pageSize; }),
        loading: Vue.computed(function () { return refs.loading; }),
        filters: Vue.computed(function () { return refs.filters; }),
        options: Vue.computed(function () { return refs.options; }),
        detailDrawer: Vue.computed({
          get: function () { return refs.detailDrawer; },
          set: function (value) { refs.detailDrawer = value; }
        }),
        detail: Vue.computed(function () { return refs.detail; }),
        detailLoading: Vue.computed(function () { return refs.detailLoading; }),
        blockPage: Vue.computed(function () { return refs.blockPage; }),
        blockDrawer: Vue.computed({
          get: function () { return refs.blockDrawer; },
          set: function (value) { refs.blockDrawer = value; }
        }),
        blockDetail: Vue.computed(function () { return refs.blockDetail; }),
        blockLoading: Vue.computed(function () { return refs.blockLoading; }),
        drawerSize: Vue.computed(function () {
          return global.innerWidth <= 768 ? '100%' : '58%';
        }),
        doSearch: doSearch,
        changeSearchSize: changeSearchSize,
        resetSearch: resetSearch,
        load: load,
        openDetail: openDetail,
        changeBlockPage: changeBlockPage,
        openBlock: openBlock,
        openDocument: openDocument,
        onTabChange: onTabChange,
        openExternal: function (url) {
          if (url) global.open(url, '_blank', 'noopener');
        },
        openRelated: function (blockId) { global.appRouter.go('analysis', { block_id: blockId }); },
        goAnalysis: function (documentId) { global.appRouter.go('analysis', { document_id: documentId }); },
        openCompare: function (documentId) { global.appRouter.go('analysis', { document_id: documentId, tab: 'compare' }); },
        statusName: function (value) { return global.utils.nameOf(global.utils.DOC_STATUS_NAMES, value); },
        validityClass: global.utils.validityClass,
        truncate: global.utils.truncate
      };
    }
  };

  global.views = global.views || {};
  global.views.documents = DocumentsView;
})(window);
