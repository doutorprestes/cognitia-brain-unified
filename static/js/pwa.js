// CognitiaBrain PWA JavaScript
let deferredPrompt;

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(reg => console.log('SW registered:', reg))
            .catch(err => console.log('SW error:', err));
    });
}

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const banner = document.getElementById('install-banner');
    if (banner) banner.style.display = 'flex';
});

async function apiCall(endpoint, options = {}) {
    try {
        const res = await fetch('/api' + endpoint, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        return await res.json();
    } catch (err) {
        showToast('Erro de conexão');
        return null;
    }
}

async function loadStats() {
    const data = await apiCall('/stats');
    if (!data) return;
    document.getElementById('stat-items').textContent = data.total_items || 0;
    document.getElementById('stat-grants').textContent = data.total_grants || 0;
    document.getElementById('stat-artigos').textContent = data.total_artigos || 0;
}

async function loadItems(type = 'all') {
    const container = document.getElementById('items-container');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    const data = await apiCall('/items?type=' + type);
    if (!data || data.items.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>Nenhum item encontrado</p></div>';
        return;
    }
    container.innerHTML = data.items.map(item => {
        return '<div class="card"><div class="card-title">' + item.title + '</div><div class="card-meta"><span>📌 ' + item.source + '</span><span>📅 ' + item.scraped_at + '</span></div><div class="card-snippet">' + (item.snippet || '') + '</div><div class="card-actions"><a href="' + item.url + '" target="_blank" class="btn btn-primary">Abrir</a><button class="btn btn-success" onclick="feedback(\'' + item.hash + '\', 1)">👍</button><button class="btn btn-danger" onclick="feedback(\'' + item.hash + '\', 0)">👎</button></div></div>';
    }).join('');
}

async function feedback(hash, label) {
    await apiCall('/feedback', {
        method: 'POST',
        body: JSON.stringify({ hash, label })
    });
    showToast(label ? '👍 Útil!' : '👎 Não útil');
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function navigate(page) {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    event.target.closest('.nav-item').classList.add('active');
    if (page === 'home') loadItems('all');
    else if (page === 'grants') loadItems('grant');
    else if (page === 'artigos') loadItems('artigo');
}

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadItems('all');
});
