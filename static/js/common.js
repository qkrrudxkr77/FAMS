// FAMS — Common JavaScript
// (토큰 흡수 로직은 base.html <head> 인라인 스크립트에서 처리)

const FAMS = {
    apiBase: '/api',

    getAuthHeader() {
        const token = localStorage.getItem('accessToken');
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    },

    async request(method, url, data = null) {
        const isFormData = data instanceof FormData;
        const isUrlSearch = data instanceof URLSearchParams;
        const headers = this.getAuthHeader();
        if (!isFormData && !isUrlSearch) headers['Content-Type'] = 'application/json';

        const options = {
            method,
            credentials: 'include',
            headers,
        };
        if (data) options.body = (isFormData || isUrlSearch) ? data : JSON.stringify(data);

        let res = await fetch(this.apiBase + url, options);

        if (res.status === 401) {
            const reissued = await this._reissueToken();
            if (!reissued) { window.location.href = '/login'; return; }

            const newHeaders = this.getAuthHeader();
            if (!isFormData && !isUrlSearch) newHeaders['Content-Type'] = 'application/json';
            options.headers = newHeaders;
            res = await fetch(this.apiBase + url, options);
        }

        return res.json();
    },

    async _reissueToken() {
        try {
            const res = await fetch(this.apiBase + '/token/reissue', { method: 'GET', credentials: 'include' });
            if (!res.ok) return false;
            const json = await res.json();
            if (json.success && json.data && json.data.access_token) {
                const token = json.data.access_token;
                localStorage.setItem('accessToken', token);
                try {
                    const raw = atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'));
                    const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
                    const payload = JSON.parse(new TextDecoder('utf-8').decode(bytes));
                    localStorage.setItem('userInfo', JSON.stringify({
                        email: payload.sub, name: payload.name, deptName: payload.deptName,
                        positionName: payload.positionName, levelName: payload.levelName,
                        deptId: payload.deptId,
                    }));
                } catch (e) { /* JWT decode 무시 */ }
                return true;
            }
        } catch (e) { /* ignore */ }
        return false;
    },

    initSidebar() {
        let userInfo = null;
        const token = localStorage.getItem('accessToken');
        if (token) {
            try {
                const raw = atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'));
                const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
                const payload = JSON.parse(new TextDecoder('utf-8').decode(bytes));
                userInfo = {
                    email: payload.sub, name: payload.name, deptName: payload.deptName,
                    positionName: payload.positionName, levelName: payload.levelName,
                    deptId: payload.deptId,
                };
                localStorage.setItem('userInfo', JSON.stringify(userInfo));
            } catch (e) {
                userInfo = this.getUserInfo();
            }
        } else {
            userInfo = this.getUserInfo();
        }
        if (!userInfo) return;

        const avatar    = document.getElementById('userAvatar');
        const userName  = document.getElementById('userName');
        const userDept  = document.getElementById('userDept');
        const userEmail = document.getElementById('userEmail');

        if (avatar) {
            avatar.style.backgroundImage = 'url(/images/default-avatar.png)';
            avatar.style.backgroundSize = 'cover';
            avatar.style.backgroundPosition = 'center';
            if (userInfo.email) {
                const img = new Image();
                img.onload = () => {
                    avatar.style.backgroundImage = `url(/api/members/photo?email=${encodeURIComponent(userInfo.email)})`;
                };
                img.src = `/api/members/photo?email=${encodeURIComponent(userInfo.email)}`;
            }
        }
        if (userName) {
            const levelPart = userInfo.levelName ? ` ${userInfo.levelName}` : '';
            userName.textContent = userInfo.name ? `${userInfo.name}${levelPart}` : '';
        }
        if (userDept)  userDept.textContent  = userInfo.deptName || '';
        if (userEmail) userEmail.textContent = userInfo.email    || '';

        // Active 메뉴 표시
        const currentPath = window.location.pathname;
        document.querySelectorAll('.sidebar-menu li.active').forEach(li => li.classList.remove('active'));
        let bestEl = null, bestLen = 0;
        document.querySelectorAll('.sidebar-menu a[href]').forEach(a => {
            const href = a.getAttribute('href');
            if (currentPath === href || currentPath.startsWith(href + '/')) {
                if (href.length > bestLen) { bestLen = href.length; bestEl = a; }
            }
        });
        if (bestEl) bestEl.closest('li').classList.add('active');
    },

    getUserInfo() {
        try { return JSON.parse(localStorage.getItem('userInfo')); }
        catch (e) { return null; }
    },

    clearAuth() {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('userInfo');
    },

    toggleSidebar() {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.toggle('collapsed');
    },
};

// ──────────────────────────────────────────
// DOMContentLoaded
// ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const publicPaths = ['/', '/login'];
    if (!publicPaths.includes(window.location.pathname)) {
        if (!localStorage.getItem('accessToken')) {
            const reissued = await FAMS._reissueToken();
            if (!reissued) {
                window.location.href = '/';
                return;
            }
        }
    }

    FAMS.initSidebar();
});
