// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

const state = {
    files: [],
    results: [],
    config: null,
    isProcessing: false,
    promptDefaults: null,
    promptOverrides: null
};

// ─────────────────────────────────────────────────────────────────────────────
// DOM Elements
// ─────────────────────────────────────────────────────────────────────────────

const elements = {
    dropZone: document.getElementById('drop-zone'),
    fileListContainer: document.getElementById('file-list-container'),
    fileList: document.getElementById('file-list'),
    fileCount: document.querySelector('.file-count'),
    resultsContainer: document.getElementById('results-container'),
    resultsList: document.getElementById('results-list'),
    generateBtn: document.getElementById('generate-btn'),
    applyBtn: document.getElementById('apply-btn'),
    undoBtn: document.getElementById('undo-btn'),
    clearBtn: document.getElementById('clear-btn'),
    addMoreBtn: document.getElementById('add-more-btn'),
    settingsBtn: document.getElementById('settings-btn'),
    settingsModal: document.getElementById('settings-modal'),
    closeSettings: document.getElementById('close-settings'),
    saveSettings: document.getElementById('save-settings'),
    progressOverlay: document.getElementById('progress-overlay'),
    progressText: document.getElementById('progress-text'),
    progressFill: document.getElementById('progress-fill'),
    cancelBtn: document.getElementById('cancel-btn'),
    status: document.getElementById('status'),
    selectAll: document.getElementById('select-all')
};

const PROVIDER_DEFAULTS = {
    ollama: {
        model: 'llava:latest',
        api_base: 'http://localhost:11434',
        needsKey: false
    },
    lmstudio: {
        model: 'llama-3.1-8b-instruct',
        api_base: 'http://localhost:1234/v1',
        needsKey: false
    },
    openai: {
        model: 'gpt-5-nano',
        api_base: 'https://api.openai.com/v1',
        needsKey: true
    },
    anthropic: {
        model: 'claude-3-haiku-20240307',
        api_base: 'https://api.anthropic.com/v1',
        needsKey: true
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────────────────────

async function init() {
    // Load config
    try {
        const configJson = await window.pywebview.api.get_config();
        state.config = JSON.parse(configJson);
        applyConfigToUI(state.config);
        await loadPromptDefaults();
        updatePromptEditor();
    } catch (e) {
        console.error('Failed to load config:', e);
    }
    
    // Check dependencies
    try {
        const depsJson = await window.pywebview.api.check_dependencies();
        const deps = JSON.parse(depsJson);
        checkDependencyWarnings(deps);
    } catch (e) {
        console.error('Failed to check dependencies:', e);
    }
    
    // Set up event listeners
    setupEventListeners();
}

function setupEventListeners() {
    // Drop zone
    elements.dropZone.addEventListener('click', selectFiles);
    elements.dropZone.addEventListener('dragover', handleDragOver);
    elements.dropZone.addEventListener('dragleave', handleDragLeave);
    elements.dropZone.addEventListener('drop', handleDrop);
    
    // File list delegation (single handler for all file items)
    setupFileListDelegation();
    
    // Results list delegation (single handler for all result interactions)
    setupResultsListDelegation();
    
    // File actions
    elements.clearBtn.addEventListener('click', clearFiles);
    elements.addMoreBtn.addEventListener('click', selectFiles);
    
    // Processing
    elements.generateBtn.addEventListener('click', startProcessing);
    elements.applyBtn.addEventListener('click', applyResults);
    elements.cancelBtn.addEventListener('click', cancelProcessing);
    elements.undoBtn.addEventListener('click', undoLast);
    
    // Settings
    elements.settingsBtn.addEventListener('click', openSettings);
    elements.closeSettings.addEventListener('click', closeSettings);
    elements.saveSettings.addEventListener('click', saveSettings);
    setupSettingsMenu();
    setupContextControls();
    setupContentControls();
    setupDateControls();
    setupPromptEditor();
    setupPromptPreviewControls();
    
    // Select all
    elements.selectAll.addEventListener('change', toggleSelectAll);
    
    // Provider change
    document.getElementById('llm-provider').addEventListener('change', handleProviderChange);
}

async function loadPromptDefaults() {
    try {
        const defaultsJson = await window.pywebview.api.get_prompt_defaults();
        state.promptDefaults = JSON.parse(defaultsJson);
    } catch (e) {
        state.promptDefaults = null;
        console.warn('Failed to load prompt defaults:', e);
    }
}

function initializePromptOverrides(prompts) {
    const empty = { image: '', video: '', document: '', generic: '' };
    state.promptOverrides = {
        system: { ...empty },
        user: { ...empty }
    };

    if (prompts?.system) {
        Object.keys(state.promptOverrides.system).forEach((key) => {
            const value = prompts.system[key];
            if (value) {
                state.promptOverrides.system[key] = value;
            }
        });
    }

    if (prompts?.user) {
        Object.keys(state.promptOverrides.user).forEach((key) => {
            const value = prompts.user[key];
            if (value) {
                state.promptOverrides.user[key] = value;
            }
        });
    }
}

function setupPromptEditor() {
    const promptType = document.getElementById('prompt-type');
    const resetBtn = document.getElementById('reset-prompts');
    const systemPrompt = document.getElementById('system-prompt');
    const userPrompt = document.getElementById('user-prompt');

    if (!promptType || !resetBtn || !systemPrompt || !userPrompt) return;

    promptType.addEventListener('change', () => {
        storePromptEdits();
        updatePromptEditor();
    });

    resetBtn.addEventListener('click', () => {
        resetPromptOverrides();
    });
}

function getPromptType() {
    const promptType = document.getElementById('prompt-type');
    return promptType?.value || 'image';
}

function storePromptEdits() {
    if (!state.promptOverrides) return;
    const type = getPromptType();
    const systemPrompt = document.getElementById('system-prompt');
    const userPrompt = document.getElementById('user-prompt');
    if (!systemPrompt || !userPrompt) return;
    state.promptOverrides.system[type] = systemPrompt.value;
    state.promptOverrides.user[type] = userPrompt.value;
}

function updatePromptEditor() {
    if (!state.promptOverrides) return;
    const type = getPromptType();
    const systemPrompt = document.getElementById('system-prompt');
    const userPrompt = document.getElementById('user-prompt');
    if (!systemPrompt || !userPrompt) return;
    systemPrompt.value = state.promptOverrides.system[type] || '';
    userPrompt.value = state.promptOverrides.user[type] || '';
}

function resetPromptOverrides() {
    if (!state.promptOverrides) return;
    const type = getPromptType();
    const defaultSystem = state.promptDefaults?.system?.[type] || '';
    state.promptOverrides.system[type] = defaultSystem;
    state.promptOverrides.user[type] = '';
    updatePromptEditor();
}

function normalizePromptValue(value) {
    const trimmed = (value || '').trim();
    return trimmed.length > 0 ? trimmed : null;
}

function buildPromptOverrides() {
    const empty = { system: {}, user: {} };
    if (!state.promptOverrides) return empty;

    const types = ['image', 'video', 'document', 'generic'];
    const defaults = state.promptDefaults?.system || {};
    const overrides = { system: {}, user: {} };

    types.forEach((type) => {
        const systemValue = normalizePromptValue(state.promptOverrides.system[type] || '');
        const defaultValue = normalizePromptValue(defaults[type] || '');
        overrides.system[type] = systemValue && systemValue === defaultValue ? null : systemValue;
        overrides.user[type] = normalizePromptValue(state.promptOverrides.user[type] || '');
    });

    return overrides;
}

function setupSettingsMenu() {
    const menuButtons = document.querySelectorAll('.menu-item');
    const sections = document.querySelectorAll('.settings-section');

    if (menuButtons.length === 0 || sections.length === 0) return;

    menuButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const targetId = button.dataset.section;
            if (!targetId) return;

            menuButtons.forEach((btn) => btn.classList.toggle('active', btn === button));
            sections.forEach((section) => {
                const isActive = section.id === targetId;
                section.classList.toggle('hidden', !isActive);
                section.classList.toggle('active', isActive);
            });
        });
    });
}

function setupContextControls() {
    const includeNeighbors = document.getElementById('include-neighbors');
    const neighborCount = document.getElementById('neighbor-count');

    if (!includeNeighbors || !neighborCount) return;

    const syncState = () => {
        neighborCount.disabled = !includeNeighbors.checked;
    };

    if (!includeNeighbors.dataset.bound) {
        includeNeighbors.dataset.bound = 'true';
        includeNeighbors.addEventListener('change', syncState);
    }
    syncState();
}

function setupContentControls() {
    const includeContent = document.getElementById('include-file-content');
    const contentMaxChars = document.getElementById('content-max-chars');

    if (!includeContent || !contentMaxChars) return;

    const syncState = () => {
        contentMaxChars.disabled = !includeContent.checked;
    };

    if (!includeContent.dataset.bound) {
        includeContent.dataset.bound = 'true';
        includeContent.addEventListener('change', syncState);
    }
    syncState();
}

function setupDateControls() {
    const includeDate = document.getElementById('include-date');
    const dateFormat = document.getElementById('date-format');

    if (!includeDate || !dateFormat) return;

    const syncState = () => {
        dateFormat.disabled = !includeDate.checked;
    };

    if (!includeDate.dataset.bound) {
        includeDate.dataset.bound = 'true';
        includeDate.addEventListener('change', syncState);
    }
    syncState();
}

function setupPromptPreviewControls() {
    const showPreview = document.getElementById('show-prompt-preview');
    const previewChars = document.getElementById('prompt-preview-chars');

    if (!showPreview || !previewChars) return;

    const syncState = () => {
        previewChars.disabled = !showPreview.checked;
    };

    if (!showPreview.dataset.bound) {
        showPreview.dataset.bound = 'true';
        showPreview.addEventListener('change', syncState);
    }
    syncState();
}

// ─────────────────────────────────────────────────────────────────────────────
// File Selection
// ─────────────────────────────────────────────────────────────────────────────

async function selectFiles() {
    try {
        const resultJson = await window.pywebview.api.select_files();
        const result = JSON.parse(resultJson);
        
        if (result.files && result.files.length > 0) {
            addFiles(result.files);
        }
    } catch (e) {
        showError('Failed to select files: ' + e.message);
    }
}

function handleDragOver(e) {
    e.preventDefault();
    if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
    }
    elements.dropZone.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    elements.dropZone.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    elements.dropZone.classList.remove('drag-over');
    // Python backend handles file path extraction via DOMEventHandler
    // and calls window.onFilesDropped() with the resolved paths
}

// Threshold for chunked rendering (tune based on performance)
const CHUNK_SIZE = 100;
const LARGE_LIST_THRESHOLD = 200;

function addFiles(filePaths) {
    // Add new files, avoiding duplicates
    const existing = new Set(state.files);
    const newFiles = filePaths.filter(f => !existing.has(f));
    
    if (newFiles.length === 0) return;
    
    // For small additions, do it synchronously
    if (newFiles.length < LARGE_LIST_THRESHOLD) {
        state.files.push(...newFiles);
        updateFileList();
        updateUI();
        return;
    }
    
    // For large additions, show progress and chunk the work
    setStatus(`Adding ${newFiles.length} files...`);
    elements.generateBtn.disabled = true;
    
    addFilesChunked(newFiles, () => {
        updateFileList();
        updateUI();
        setStatus(`Added ${newFiles.length} files`);
    });
}

function addFilesChunked(files, onComplete) {
    let index = 0;
    
    function processChunk() {
        const end = Math.min(index + CHUNK_SIZE, files.length);
        
        // Add chunk to state
        while (index < end) {
            state.files.push(files[index]);
            index++;
        }
        
        // Update count immediately for feedback
        elements.fileCount.textContent = `${state.files.length} file${state.files.length !== 1 ? 's' : ''} selected (loading...)`;
        
        if (index < files.length) {
            // More to process - schedule next chunk
            requestAnimationFrame(processChunk);
        } else {
            // All done
            onComplete();
        }
    }
    
    requestAnimationFrame(processChunk);
}

function clearFiles() {
    state.files = [];
    state.results = [];
    updateFileList();
    updateUI();
}

function updateFileList() {
    const totalFiles = state.files.length;
    
    // For small lists, render synchronously with DocumentFragment
    if (totalFiles < LARGE_LIST_THRESHOLD) {
        renderFileListSync();
        return;
    }
    
    // For large lists, render in chunks to keep UI responsive
    renderFileListChunked();
}

function renderFileListSync() {
    const fragment = document.createDocumentFragment();
    
    state.files.forEach((filePath, index) => {
        fragment.appendChild(createFileItem(filePath, index));
    });
    
    elements.fileList.innerHTML = '';
    elements.fileList.appendChild(fragment);
    elements.fileCount.textContent = `${state.files.length} file${state.files.length !== 1 ? 's' : ''} selected`;
}

function renderFileListChunked() {
    const totalFiles = state.files.length;
    let index = 0;
    
    // Clear and show loading state
    elements.fileList.innerHTML = '';
    elements.fileCount.textContent = `${totalFiles} files (rendering...)`;
    
    function renderChunk() {
        const fragment = document.createDocumentFragment();
        const end = Math.min(index + CHUNK_SIZE, totalFiles);
        
        while (index < end) {
            fragment.appendChild(createFileItem(state.files[index], index));
            index++;
        }
        
        elements.fileList.appendChild(fragment);
        
        if (index < totalFiles) {
            // More to render - schedule next chunk
            requestAnimationFrame(renderChunk);
        } else {
            // Done rendering
            elements.fileCount.textContent = `${totalFiles} file${totalFiles !== 1 ? 's' : ''} selected`;
        }
    }
    
    requestAnimationFrame(renderChunk);
}

function createFileItem(filePath, index) {
    const fileName = filePath.split('/').pop();
    const li = document.createElement('li');
    li.className = 'file-item';
    li.dataset.index = index;
    li.innerHTML = `
        <span class="file-name">${escapeHtml(fileName)}</span>
        <button class="btn btn-icon btn-remove" data-index="${index}">×</button>
    `;
    return li;
}

// Event delegation for file list - single handler for all remove buttons
function setupFileListDelegation() {
    elements.fileList.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.btn-remove');
        if (removeBtn) {
            const index = parseInt(removeBtn.dataset.index, 10);
            if (!isNaN(index) && index >= 0 && index < state.files.length) {
                state.files.splice(index, 1);
                updateFileList();
                updateUI();
            }
        }
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Processing
// ─────────────────────────────────────────────────────────────────────────────

async function startProcessing() {
    if (state.files.length === 0) return;
    
    state.isProcessing = true;
    showProgress('Starting...');
    
    try {
        const resultJson = await window.pywebview.api.start_processing(
            JSON.stringify(state.files)
        );
        const result = JSON.parse(resultJson);
        
        if (result.error) {
            throw new Error(result.error);
        }
    } catch (e) {
        hideProgress();
        showError('Failed to start processing: ' + e.message);
        state.isProcessing = false;
    }
}

// Called from Python via evaluate_js
window.onProcessingStatus = function(statusJson) {
    const status = typeof statusJson === 'string' ? JSON.parse(statusJson) : statusJson;
    
    const percent = status.progress_percent || 0;
    elements.progressFill.style.width = `${percent}%`;
    
    if (status.current_file) {
        elements.progressText.textContent = `Processing: ${status.current_file} (${status.current_index}/${status.total_files})`;
    } else {
        elements.progressText.textContent = status.message || 'Processing...';
    }
};

window.onProcessingComplete = function(resultJson) {
    const data = typeof resultJson === 'string' ? JSON.parse(resultJson) : resultJson;
    state.results = data.results || [];
    state.isProcessing = false;
    
    hideProgress();
    displayResults();
    updateUI();
    
    setStatus(`Generated ${state.results.length} suggestions`);
};

window.onProcessingError = function(errorJson) {
    const data = typeof errorJson === 'string' ? JSON.parse(errorJson) : errorJson;
    state.isProcessing = false;
    
    hideProgress();
    showError(data.error || 'Processing failed');
};

window.onFilesDropped = function(pathsJson) {
    const paths = typeof pathsJson === 'string' ? JSON.parse(pathsJson) : pathsJson;
    if (Array.isArray(paths) && paths.length > 0) {
        addFiles(paths);
        setStatus(`Added ${paths.length} dropped file${paths.length !== 1 ? 's' : ''}`);
    }
};

function cancelProcessing() {
    window.pywebview.api.stop_processing();
    elements.progressText.textContent = 'Cancelling...';
}

// ─────────────────────────────────────────────────────────────────────────────
// Results Display
// ─────────────────────────────────────────────────────────────────────────────

function displayResults() {
    // Normalize status first
    state.results.forEach(r => {
        if (r.status === 'pending') r.status = 'approved';
    });
    
    const totalResults = state.results.length;
    
    // For small result sets, render synchronously
    if (totalResults < LARGE_LIST_THRESHOLD) {
        renderResultsSync();
    } else {
        renderResultsChunked();
    }
    
    elements.resultsContainer.classList.remove('hidden');
    updateApplyButton();
    syncSelectAll();
}

function renderResultsSync() {
    const fragment = document.createDocumentFragment();
    
    state.results.forEach((result, index) => {
        fragment.appendChild(createResultItem(result, index));
    });
    
    elements.resultsList.innerHTML = '';
    elements.resultsList.appendChild(fragment);
}

function renderResultsChunked() {
    const totalResults = state.results.length;
    let index = 0;
    
    elements.resultsList.innerHTML = '';
    setStatus(`Rendering ${totalResults} results...`);
    
    function renderChunk() {
        const fragment = document.createDocumentFragment();
        const end = Math.min(index + CHUNK_SIZE, totalResults);
        
        while (index < end) {
            fragment.appendChild(createResultItem(state.results[index], index));
            index++;
        }
        
        elements.resultsList.appendChild(fragment);
        
        if (index < totalResults) {
            requestAnimationFrame(renderChunk);
        } else {
            setStatus(`Generated ${totalResults} suggestions`);
        }
    }
    
    requestAnimationFrame(renderChunk);
}

function createResultItem(result, index) {
    const tagValue = result.tags && result.tags.length > 0 ? result.tags.join(', ') : '';
    const canApplyTags = state.config?.processing?.auto_apply_tags !== false;
    const applyTags = result.apply_tags ?? canApplyTags;
    result.apply_tags = applyTags;
    const tagsDisabled = !canApplyTags || !applyTags;
    const showPromptPreview = state.config?.show_prompt_preview;
    const systemPrompt = result.system_prompt || '';
    const userPrompt = result.user_prompt || '';
    const promptPreview = showPromptPreview && (systemPrompt || userPrompt)
        ? `
            <details class="prompt-preview">
                <summary>Prompt preview</summary>
                ${systemPrompt ? `
                    <div class="prompt-block">
                        <div class="prompt-label">System</div>
                        <pre>${escapeHtml(systemPrompt)}</pre>
                    </div>
                ` : ''}
                ${userPrompt ? `
                    <div class="prompt-block">
                        <div class="prompt-label">User</div>
                        <pre>${escapeHtml(userPrompt)}</pre>
                    </div>
                ` : ''}
            </details>
        `
        : '';
    
    const li = document.createElement('li');
    li.className = `result-item ${result.status}`;
    li.dataset.index = index;
    li.innerHTML = `
        <label class="result-checkbox">
            <input type="checkbox" class="result-select" data-index="${index}" 
                ${result.status === 'approved' ? 'checked' : ''}
                ${result.status === 'failed' ? 'disabled' : ''}>
        </label>
        <div class="result-names">
            <span class="original-name">${escapeHtml(result.original_name)}</span>
            <span class="arrow">→</span>
            <input type="text" class="new-name-input" data-index="${index}"
                value="${escapeHtml(result.final_name || result.suggested_name)}"
                ${result.status === 'failed' ? 'disabled' : ''}>
        </div>
        <div class="result-meta">
            ${result.confidence ? `<span class="confidence">${Math.round(result.confidence * 100)}%</span>` : ''}
        </div>
        <div class="result-tags">
            <label class="checkbox">
                <input type="checkbox" class="apply-tags-toggle" data-index="${index}"
                    ${applyTags ? 'checked' : ''}
                    ${canApplyTags ? '' : 'disabled'}>
                <span>Apply tags</span>
            </label>
            <input type="text" class="tags-input" data-index="${index}"
                value="${escapeHtml(tagValue)}" placeholder="tag1, tag2"
                ${tagsDisabled ? 'disabled' : ''}>
        </div>
        ${state.config?.show_reasoning && result.reasoning ? `<div class="result-reasoning">${escapeHtml(result.reasoning)}</div>` : ''}
        ${promptPreview}
        ${result.error_message ? `<div class="result-error">${escapeHtml(result.error_message)}</div>` : ''}
    `;
    return li;
}

// Event delegation for results list - single handler for all interactions
function setupResultsListDelegation() {
    elements.resultsList.addEventListener('change', (e) => {
        const target = e.target;
        const index = parseInt(target.dataset.index, 10);
        
        if (isNaN(index) || index < 0 || index >= state.results.length) return;
        
        if (target.classList.contains('result-select')) {
            state.results[index].status = target.checked ? 'approved' : 'rejected';
            updateApplyButton();
            syncSelectAll();
        } else if (target.classList.contains('new-name-input')) {
            state.results[index].final_name = target.value;
        } else if (target.classList.contains('tags-input')) {
            const raw = target.value || '';
            const tags = raw
                .split(',')
                .map((tag) => tag.trim())
                .filter(Boolean)
                .slice(0, 10);
            state.results[index].tags = tags;
        } else if (target.classList.contains('apply-tags-toggle')) {
            const applyTags = target.checked;
            state.results[index].apply_tags = applyTags;
            const tagsInput = elements.resultsList.querySelector(`.tags-input[data-index="${index}"]`);
            if (tagsInput) {
                tagsInput.disabled = !applyTags;
            }
        }
    });
}

function toggleSelectAll(e) {
    const checked = e.target.checked;
    state.results.forEach(r => {
        if (r.status !== 'failed') {
            r.status = checked ? 'approved' : 'rejected';
        }
    });
    
    elements.resultsList.querySelectorAll('.result-select:not(:disabled)').forEach(cb => {
        cb.checked = checked;
    });
    
    updateApplyButton();
    elements.selectAll.indeterminate = false;
}

function updateApplyButton() {
    const approvedCount = state.results.filter(r => r.status === 'approved').length;
    elements.applyBtn.textContent = `Apply Selected (${approvedCount})`;
    elements.applyBtn.disabled = approvedCount === 0;
}

function syncSelectAll() {
    const selectable = state.results.filter(r => r.status !== 'failed');
    if (selectable.length === 0) {
        elements.selectAll.checked = false;
        elements.selectAll.indeterminate = false;
        return;
    }
    const approvedCount = selectable.filter(r => r.status === 'approved').length;
    elements.selectAll.checked = approvedCount === selectable.length;
    elements.selectAll.indeterminate = approvedCount > 0 && approvedCount < selectable.length;
}

// ─────────────────────────────────────────────────────────────────────────────
// Apply & Undo
// ─────────────────────────────────────────────────────────────────────────────

async function applyResults() {
    const toApply = state.results.filter(r => r.status === 'approved');
    if (toApply.length === 0) return;

    const isDryRun = state.config?.processing?.dry_run;
    const shouldConfirm = state.config?.confirm_before_apply !== false;

    if (shouldConfirm) {
        const message = isDryRun
            ? `Dry run is enabled. Preview ${toApply.length} changes?`
            : `Apply ${toApply.length} changes?`;
        if (!confirm(message)) {
            return;
        }
    }
    
    const progressMessage = isDryRun
        ? `Previewing ${toApply.length} changes...`
        : `Applying ${toApply.length} changes...`;
    showProgress(progressMessage);
    
    try {
        const resultJson = await window.pywebview.api.apply_results(
            JSON.stringify(toApply)
        );
        const result = JSON.parse(resultJson);
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        hideProgress();
        if (result.dry_run) {
            const previewCount = result.preview_count ?? toApply.length;
            setStatus(`Dry run: previewed ${previewCount} changes`);
            return;
        }

        setStatus(`Renamed ${result.applied_count} files`);
        
        // Clear and refresh
        clearFiles();
        elements.undoBtn.classList.remove('hidden');
        
    } catch (e) {
        hideProgress();
        showError('Failed to apply changes: ' + e.message);
    }
}

async function undoLast() {
    try {
        const resultJson = await window.pywebview.api.undo_last_batch();
        const result = JSON.parse(resultJson);
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        setStatus(`Restored ${result.restored_count} files`);
        
        if (result.errors && result.errors.length > 0) {
            showError('Some files could not be restored:\n' + result.errors.join('\n'));
        }
        
    } catch (e) {
        showError('Failed to undo: ' + e.message);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings
// ─────────────────────────────────────────────────────────────────────────────

function openSettings() {
    elements.settingsModal.classList.remove('hidden');
}

function closeSettings() {
    elements.settingsModal.classList.add('hidden');
}

async function saveSettings() {
    storePromptEdits();
    const provider = document.getElementById('llm-provider').value;
    const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.ollama;
    const apiBaseValue = document.getElementById('api-base').value || defaults.api_base;
    const apiKeyValue = document.getElementById('api-key').value || null;
    const temperatureValue = parseFloat(document.getElementById('llm-temperature').value);
    const timeoutValue = parseInt(document.getElementById('llm-timeout').value, 10);
    const neighborCountValue = parseInt(document.getElementById('neighbor-count').value, 10);
    const maxConcurrencyValue = parseInt(document.getElementById('max-concurrency').value, 10);
    const videoExtractCountValue = parseInt(document.getElementById('video-extract-count').value, 10);
    const folderContextDepthValue = parseInt(document.getElementById('folder-context-depth').value, 10);
    const includeNeighbors = document.getElementById('include-neighbors').checked;
    const includeFileContent = document.getElementById('include-file-content').checked;
    const contentMaxCharsValue = parseInt(document.getElementById('content-max-chars').value, 10);
    const tagCountValue = parseInt(document.getElementById('tag-count').value, 10);
    const dropFolderDepthValue = parseInt(document.getElementById('drop-folder-depth').value, 10);
    const tagPromptValue = document.getElementById('tag-prompt').value;
    const showPromptPreview = document.getElementById('show-prompt-preview').checked;
    const promptPreviewCharsValue = parseInt(document.getElementById('prompt-preview-chars').value, 10);
    const neighborCountFinal = includeNeighbors
        ? (Number.isFinite(neighborCountValue) ? neighborCountValue : 3)
        : 0;

    const config = {
        llm: {
            provider: provider,
            model: document.getElementById('llm-model').value,
            api_key: apiKeyValue,
            api_base: apiBaseValue,
            image_mode: document.getElementById('llm-image-mode').value,
            temperature: Number.isFinite(temperatureValue) ? temperatureValue : 0.3,
            timeout_seconds: Number.isFinite(timeoutValue) ? timeoutValue : 60
        },
        processing: {
            case_style: document.getElementById('case-style').value,
            preserve_extension: document.getElementById('preserve-extension').checked,
            include_date_prefix: document.getElementById('include-date').checked,
            date_format: document.getElementById('date-format').value || '%Y-%m-%d',
            include_current_filename: document.getElementById('include-current-filename').checked,
            include_parent_folder: document.getElementById('include-parent-folder').checked,
            include_neighbor_names: includeNeighbors,
            neighbor_context_count: neighborCountFinal,
            folder_context_depth: Number.isFinite(folderContextDepthValue) ? folderContextDepthValue : 1,
            include_file_content: includeFileContent,
            content_max_chars: Number.isFinite(contentMaxCharsValue) ? contentMaxCharsValue : 2000,
            video_extract_count: Number.isFinite(videoExtractCountValue) ? videoExtractCountValue : 3,
            max_concurrency: Number.isFinite(maxConcurrencyValue) ? maxConcurrencyValue : 1,
            auto_apply_tags: document.getElementById('auto-tags').checked,
            tag_count: Number.isFinite(tagCountValue) ? tagCountValue : 5,
            tag_prompt: tagPromptValue,
            tag_mode: document.getElementById('tag-mode').value,
            drop_folder_depth: Number.isFinite(dropFolderDepthValue) ? dropFolderDepthValue : 1,
            dry_run: document.getElementById('dry-run').checked
        },
        confirm_before_apply: document.getElementById('confirm-apply').checked,
        show_reasoning: document.getElementById('show-reasoning').checked,
        show_prompt_preview: showPromptPreview,
        prompt_preview_chars: Number.isFinite(promptPreviewCharsValue) ? promptPreviewCharsValue : 2000,
        prompts: buildPromptOverrides()
    };
    
    try {
        const resultJson = await window.pywebview.api.save_config(JSON.stringify(config));
        const result = JSON.parse(resultJson);
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        state.config = config;
        closeSettings();
        setStatus('Settings saved');
        if (state.results.length > 0) {
            displayResults();
        }
        
    } catch (e) {
        showError('Failed to save settings: ' + e.message);
    }
}

function applyConfigToUI(config) {
    if (!config) return;
    
    if (config.llm) {
        document.getElementById('llm-provider').value = config.llm.provider || 'ollama';
        document.getElementById('llm-model').value = config.llm.model || 'llava:latest';
        document.getElementById('api-base').value = config.llm.api_base || 'http://localhost:11434';
        document.getElementById('api-key').value = config.llm.api_key || '';
        document.getElementById('llm-image-mode').value = config.llm.image_mode || 'auto';
        document.getElementById('llm-temperature').value = config.llm.temperature ?? 0.3;
        document.getElementById('llm-timeout').value = config.llm.timeout_seconds ?? 60;
        handleProviderChange({ preserveValues: true });
    }
    
    if (config.processing) {
        document.getElementById('case-style').value = config.processing.case_style || 'kebabCase';
        document.getElementById('preserve-extension').checked = config.processing.preserve_extension !== false;
        document.getElementById('include-date').checked = config.processing.include_date_prefix || false;
        document.getElementById('date-format').value = config.processing.date_format || '%Y-%m-%d';
        document.getElementById('include-current-filename').checked = config.processing.include_current_filename !== false;
        document.getElementById('include-parent-folder').checked = config.processing.include_parent_folder || false;
        document.getElementById('include-neighbors').checked = config.processing.include_neighbor_names !== false;
        document.getElementById('neighbor-count').value = config.processing.neighbor_context_count ?? 3;
        document.getElementById('folder-context-depth').value = config.processing.folder_context_depth ?? 1;
        document.getElementById('include-file-content').checked = config.processing.include_file_content || false;
        document.getElementById('content-max-chars').value = config.processing.content_max_chars ?? 2000;
        document.getElementById('video-extract-count').value = config.processing.video_extract_count ?? 3;
        document.getElementById('max-concurrency').value = config.processing.max_concurrency ?? 1;
        document.getElementById('auto-tags').checked = config.processing.auto_apply_tags !== false;
        document.getElementById('tag-count').value = config.processing.tag_count ?? 5;
        document.getElementById('tag-prompt').value = config.processing.tag_prompt || '';
        document.getElementById('tag-mode').value = config.processing.tag_mode || 'append';
        document.getElementById('drop-folder-depth').value = config.processing.drop_folder_depth ?? 1;
        document.getElementById('dry-run').checked = config.processing.dry_run || false;
    }

    document.getElementById('confirm-apply').checked = config.confirm_before_apply !== false;
    document.getElementById('show-reasoning').checked = config.show_reasoning !== false;
    document.getElementById('show-prompt-preview').checked = config.show_prompt_preview || false;
    document.getElementById('prompt-preview-chars').value = config.prompt_preview_chars ?? 2000;

    setupContextControls();
    setupContentControls();
    setupDateControls();
    setupPromptPreviewControls();
    initializePromptOverrides(config.prompts);
    updatePromptEditor();
}

function handleProviderChange(eventOrOptions) {
    const preserveValues = eventOrOptions && eventOrOptions.preserveValues === true;
    const provider = document.getElementById('llm-provider').value;
    const apiKeyGroup = document.getElementById('api-key-group');
    const modelInput = document.getElementById('llm-model');
    const apiBaseInput = document.getElementById('api-base');
    const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.ollama;
    
    apiKeyGroup.style.display = defaults.needsKey ? 'block' : 'none';

    if (preserveValues) {
        if (!modelInput.value) {
            modelInput.value = defaults.model;
        }
        if (!apiBaseInput.value) {
            apiBaseInput.value = defaults.api_base;
        }
        return;
    }

    modelInput.value = defaults.model;
    apiBaseInput.value = defaults.api_base;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────────────────────

function updateUI() {
    const hasFiles = state.files.length > 0;
    const hasResults = state.results.length > 0;
    
    elements.dropZone.classList.toggle('hidden', hasFiles);
    elements.fileListContainer.classList.toggle('hidden', !hasFiles);
    elements.generateBtn.disabled = !hasFiles || state.isProcessing;
    elements.applyBtn.classList.toggle('hidden', !hasResults);
    elements.resultsContainer.classList.toggle('hidden', !hasResults);
}

function showProgress(message) {
    elements.progressText.textContent = message;
    elements.progressFill.style.width = '0%';
    elements.progressOverlay.classList.remove('hidden');
}

function hideProgress() {
    elements.progressOverlay.classList.add('hidden');
}

function setStatus(message) {
    elements.status.textContent = message;
}

function showError(message) {
    alert(message); // Simple for now - could be a toast
    setStatus('Error occurred');
}

function checkDependencyWarnings(deps) {
    const warnings = [];
    
    if (!deps.tag?.available) {
        warnings.push('macOS tag CLI not found. Tags will not be applied.\nInstall with: brew install tag');
    }
    
    if (!deps.ffprobe?.available) {
        warnings.push('ffprobe not found. Video metadata will be limited.\nInstall with: brew install ffmpeg');
    }

    if (!deps.ffmpeg?.available) {
        warnings.push('ffmpeg not found. Video frame extraction will be skipped.\nInstall with: brew install ffmpeg');
    }

    if (!deps.pypdf?.available) {
        warnings.push('pypdf not found. PDF content extraction will be skipped.\nInstall with: pip install pypdf');
    }

    if (!deps.markitdown?.available) {
        warnings.push('markitdown not found. Office document extraction will be limited.\nInstall with: pip install markitdown');
    }

    if (!deps.textutil?.available) {
        warnings.push('textutil not found. Legacy document extraction will be limited.');
    }
    
    if (warnings.length > 0) {
        console.warn('Dependency warnings:', warnings);
        showDependencyWarning(warnings);
    }
}

function showDependencyWarning(warnings) {
    // Create a dismissible warning banner
    const existingBanner = document.querySelector('.dependency-warning');
    if (existingBanner) existingBanner.remove();
    
    const banner = document.createElement('div');
    banner.className = 'dependency-warning';
    banner.innerHTML = `
        <div class="warning-content">
            <span class="warning-icon">⚠️</span>
            <span class="warning-text">
                <strong>Missing dependencies:</strong> 
                ${warnings.length === 1 
                    ? warnings[0].split('\n')[0] 
                    : `${warnings.length} optional tools not found`}
            </span>
            <button class="warning-details-btn" title="Show details">ℹ️</button>
            <button class="warning-dismiss-btn" title="Dismiss">×</button>
        </div>
    `;
    
    const detailsBtn = banner.querySelector('.warning-details-btn');
    detailsBtn.addEventListener('click', () => {
        alert('Missing Dependencies:\n\n' + warnings.join('\n\n'));
    });
    
    const dismissBtn = banner.querySelector('.warning-dismiss-btn');
    dismissBtn.addEventListener('click', () => banner.remove());
    
    document.body.insertBefore(banner, document.body.firstChild);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ─────────────────────────────────────────────────────────────────────────────
// Initialize on load
// ─────────────────────────────────────────────────────────────────────────────

if (window.pywebview) {
    init();
} else {
    window.addEventListener('pywebviewready', init);
}
