// DOM Elements
const searchInput = document.getElementById('search-input');
const clearBtn = document.getElementById('clear-btn');
const loadingIndicator = document.getElementById('loading-indicator');
const dropdown = document.getElementById('suggestions-dropdown');
const suggestionsList = document.getElementById('suggestions-list');
const searchBtn = document.getElementById('search-btn');
const trendingTags = document.getElementById('trending-tags');
const statusToast = document.getElementById('status-toast');

// Debugger Elements
const debugPrefix = document.getElementById('debug-prefix');
const debugNode = document.getElementById('debug-node');
const debugStatus = document.getElementById('debug-status');

// Metrics Elements
const metricHitRate = document.getElementById('metric-hit-rate');
const metricHits = document.getElementById('metric-hits');
const metricMisses = document.getElementById('metric-misses');
const metricBuffer = document.getElementById('metric-buffer');
const bufferRatio = document.getElementById('buffer-ratio');
const bufferProgress = document.getElementById('buffer-progress');

// Application State
let suggestions = [];
let focusedIndex = -1;
let debounceTimeout = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    fetchTrending();
    updateMetrics();
    // Poll metrics every 3 seconds to keep stats fresh
    setInterval(updateMetrics, 3000);
});

// Event Listeners
searchInput.addEventListener('input', () => {
    const val = searchInput.value;
    
    // Toggle clear button
    if (val.length > 0) {
        clearBtn.classList.remove('hidden');
    } else {
        clearBtn.classList.add('hidden');
        closeDropdown();
        resetDebugger();
        return;
    }
    
    // Debounce suggestion fetching (300ms)
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
        getSuggestions(val);
    }, 300);
});

clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    closeDropdown();
    resetDebugger();
    searchInput.focus();
});

searchBtn.addEventListener('click', () => {
    const val = searchInput.value.trim();
    if (val) submitSearch(val);
});

// Keyboard Navigation inside Dropdown
searchInput.addEventListener('keydown', (e) => {
    const items = suggestionsList.getElementsByTagName('li');
    
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (items.length === 0) return;
        focusedIndex = (focusedIndex + 1) % items.length;
        highlightItem(items);
    } 
    else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (items.length === 0) return;
        focusedIndex = (focusedIndex - 1 + items.length) % items.length;
        highlightItem(items);
    } 
    else if (e.key === 'Enter') {
        e.preventDefault();
        if (focusedIndex > -1 && items[focusedIndex]) {
            // Select suggestion
            const selectedQuery = suggestions[focusedIndex].query;
            searchInput.value = selectedQuery;
            closeDropdown();
            submitSearch(selectedQuery);
        } else {
            // Submit direct search input
            const val = searchInput.value.trim();
            if (val) submitSearch(val);
        }
    } 
    else if (e.key === 'Escape') {
        closeDropdown();
    }
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!dropdown.contains(e.target) && e.target !== searchInput) {
        closeDropdown();
    }
});

// Highlight suggestion helper
function highlightItem(items) {
    // Remove focused class from all
    for (let i = 0; i < items.length; i++) {
        items[i].classList.remove('focused');
    }
    
    // Add to focused one and scroll into view if needed
    if (focusedIndex > -1 && items[focusedIndex]) {
        items[focusedIndex].classList.add('focused');
        searchInput.value = suggestions[focusedIndex].query;
        // Update debugger for the currently highlighted suggestion
        updateDebugger(suggestions[focusedIndex].query);
    }
}

// Fetch Autocomplete Suggestions
async function getSuggestions(prefix) {
    if (!prefix.trim()) return;
    
    loadingIndicator.classList.remove('hidden');
    
    try {
        const response = await fetch(`/suggest?q=${encodeURIComponent(prefix)}`);
        if (!response.ok) throw new Error('API failure');
        
        suggestions = await response.json();
        
        displaySuggestions(suggestions);
        updateDebugger(prefix);
    } catch (err) {
        console.error('Error fetching suggestions:', err);
    } finally {
        loadingIndicator.classList.add('hidden');
    }
}

// Render dropdown list
function displaySuggestions(items) {
    suggestionsList.innerHTML = '';
    focusedIndex = -1;
    
    if (items.length === 0) {
        closeDropdown();
        return;
    }
    
    items.forEach((item, index) => {
        const li = document.createElement('li');
        
        // Match highlight logic (optional, keeping it simple)
        const qSpan = document.createElement('span');
        qSpan.textContent = item.query;
        
        const scoreSpan = document.createElement('span');
        scoreSpan.className = 'score-badge';
        scoreSpan.textContent = `score: ${Math.round(item.score)}`;
        
        li.appendChild(qSpan);
        li.appendChild(scoreSpan);
        
        li.addEventListener('click', () => {
            searchInput.value = item.query;
            closeDropdown();
            submitSearch(item.query);
        });
        
        suggestionsList.appendChild(li);
    });
    
    const searchWrapper = document.querySelector('.search-input-wrapper');
    searchWrapper.classList.add('dropdown-open');
    dropdown.classList.remove('hidden');
}

function closeDropdown() {
    dropdown.classList.add('hidden');
    const searchWrapper = document.querySelector('.search-input-wrapper');
    if (searchWrapper) searchWrapper.classList.remove('dropdown-open');
    focusedIndex = -1;
}

// Debugger Updates: Consistent Hash Ring and Cache Routing
async function updateDebugger(prefix) {
    if (!prefix.trim()) return;
    
    try {
        const response = await fetch(`/cache/debug?prefix=${encodeURIComponent(prefix)}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        debugPrefix.textContent = `"${data.prefix}"`;
        debugNode.textContent = data.selected_node;
        
        // Status Badge Style
        debugStatus.textContent = data.cache_status;
        debugStatus.className = 'value status-badge ' + data.cache_status.toLowerCase();
        
        // Ring Node Activation Style
        document.querySelectorAll('.node-indicator').forEach(el => el.classList.remove('active'));
        const activeIndicator = document.getElementById(`indicator-${data.selected_node}`);
        if (activeIndicator) {
            activeIndicator.classList.add('active');
        }
        
    } catch (err) {
        console.error('Error fetching debug info:', err);
    }
}

function resetDebugger() {
    debugPrefix.textContent = '-';
    debugNode.textContent = '-';
    debugStatus.textContent = '-';
    debugStatus.className = 'debug-value status-badge';
    document.querySelectorAll('.node-indicator').forEach(el => el.classList.remove('active'));
}

// Submit Search API Query
async function submitSearch(query) {
    try {
        const response = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        
        if (!response.ok) throw new Error('Search failed');
        
        // UI confirmation
        showToast(`🎉 Search query "${query}" submitted and buffered successfully!`);
        
        // Refresh metrics immediately
        updateMetrics();
        
        // Reload trending searches
        fetchTrending();
        
    } catch (err) {
        console.error('Error submitting search:', err);
        showToast('❌ Error submitting search. Please try again.', true);
    }
}

function showToast(message, isError = false) {
    statusToast.textContent = message;
    statusToast.style.background = isError ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)';
    statusToast.style.borderColor = isError ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)';
    statusToast.style.color = isError ? '#f87171' : '#a7f3d0';
    
    statusToast.classList.remove('hidden');
    
    setTimeout(() => {
        statusToast.classList.add('hidden');
    }, 4000);
}

// Fetch Overall Trending Searches
async function fetchTrending() {
    try {
        // Querying empty prefix retrieves top trending searches overall
        const response = await fetch('/suggest?q=');
        if (!response.ok) return;
        
        const data = await response.json();
        
        trendingTags.innerHTML = '';
        if (data.length === 0) {
            trendingTags.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.85rem;">No trending items yet</span>';
            return;
        }
        
        data.slice(0, 5).forEach(item => {
            const tag = document.createElement('span');
            tag.className = 'trending-chip';
            tag.textContent = item.query;
            tag.addEventListener('click', () => {
                searchInput.value = item.query;
                submitSearch(item.query);
            });
            trendingTags.appendChild(tag);
        });
    } catch (err) {
        console.error('Error fetching trending searches:', err);
    }
}

// Refresh Performance & Buffer Metrics
async function updateMetrics() {
    try {
        const response = await fetch('/metrics');
        if (!response.ok) return;
        
        const data = await response.json();
        
        const newHitRateStr = `${(data.cache_hit_rate * 100).toFixed(1)}%`;
        if (metricHitRate.textContent !== newHitRateStr) {
            metricHitRate.textContent = newHitRateStr;
            metricHitRate.classList.remove('pulse-anim');
            void metricHitRate.offsetWidth; // trigger reflow
            metricHitRate.classList.add('pulse-anim');
        }
        metricHits.textContent = data.cache_hits;
        metricMisses.textContent = data.cache_misses;
        metricBuffer.textContent = data.buffer_accumulated_updates;
        
        // Progress bar for the buffer size (0 to 100)
        const size = data.buffer_accumulated_updates;
        bufferRatio.textContent = `${size}/100`;
        bufferProgress.style.width = `${Math.min(size, 100)}%`;
        
        // Color transition for buffer ratio
        if (size >= 80) {
            bufferProgress.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
        } else {
            bufferProgress.style.background = 'linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%)';
        }
        
    } catch (err) {
        console.error('Error updating metrics:', err);
    }
}
