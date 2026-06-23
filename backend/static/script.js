document.addEventListener("DOMContentLoaded", () => {
    // UI Elements
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    const btnAnalyze = document.getElementById("btn-analyze");
    const btnDownload = document.getElementById("btn-download");
    const btnCloseError = document.getElementById("btn-close-error");
    
    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingMessage = document.getElementById("loading-message");
    const errorModal = document.getElementById("error-modal");
    const errorText = document.getElementById("error-text");
    const errorDetails = document.getElementById("error-details");
    
    const resultsPanel = document.getElementById("results-panel");
    const reportTitle = document.getElementById("report-title");
    
    // Stats elements
    const statCompared = document.getElementById("stat-compared");
    const statAdded = document.getElementById("stat-added");
    const statDeleted = document.getElementById("stat-deleted");
    const statChanged = document.getElementById("stat-changed");
    const statInstAdded = document.getElementById("stat-inst-added");
    const statInstDeleted = document.getElementById("stat-inst-deleted");
    const statImpact = document.getElementById("stat-impact");
    
    const eventsTimeline = document.getElementById("events-timeline");
    const listFunctions = document.getElementById("list-functions");
    
    const currentFunctionName = document.getElementById("current-function-name");
    const functionMetadata = document.getElementById("function-metadata");
    const functionContentWrapper = document.getElementById("function-content-wrapper");
    const noFunctionSelected = document.getElementById("no-function-selected");
    
    const localEventsList = document.getElementById("local-events-list");
    const cfgGraphOld = document.getElementById("cfg-graph-old");
    const cfgGraphNew = document.getElementById("cfg-graph-new");
    const blockDiffsContainer = document.getElementById("block-diffs-container");

    // Textareas start empty by default

    // Active Tab State
    let activeTab = "ir-mode";
    let lastAnalysisData = null;

    // Tab Switching
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            activeTab = btn.getAttribute("data-tab");
            document.getElementById(`${activeTab}-content`).classList.add("active");
        });
    });

    // File Upload handling
    function bindFileUpload(fileInputId, textAreaId) {
        document.getElementById(fileInputId).addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (evt) => {
                document.getElementById(textAreaId).value = evt.target.result;
            };
            reader.readAsText(file);
        });
    }

    bindFileUpload("file-ir1", "text-ir1");
    bindFileUpload("file-ir2", "text-ir2");
    bindFileUpload("file-code1", "text-code1");
    bindFileUpload("file-code2", "text-code2");

    btnCloseError.addEventListener("click", () => {
        errorModal.classList.add("hidden");
    });

    function getPayload() {
        if (activeTab === "ir-mode") {
            return {
                mode: "ir",
                ir1: document.getElementById("text-ir1").value,
                ir2: document.getElementById("text-ir2").value
            };
        } else {
            return {
                mode: "code",
                code1: document.getElementById("text-code1").value,
                code2: document.getElementById("text-code2").value,
                opt1: document.getElementById("opt-level-1").value,
                opt2: document.getElementById("opt-level-2").value,
                lang: document.getElementById("select-lang").value,
                extra_flags: document.getElementById("input-flags").value
            };
        }
    }

    btnAnalyze.addEventListener("click", async () => {
        showLoading("Analyzing compiler IR structures...");
        const payload = getPayload();
        
        try {
            const response = await fetch("/api/analyze", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                showError(data.error || "Analysis failed", data.details || "");
                hideLoading();
                return;
            }
            
            lastAnalysisData = data;
            console.log("API Response:", JSON.stringify(data.stats));
            console.log("Changed functions:", Object.keys(data.changed_functions));
            renderResults(data);
            hideLoading();
            
        } catch (err) {
            showError("Network/Server Error", err.toString());
            hideLoading();
        }
    });

    const btnExportCsv = document.getElementById("btn-export-csv");
    const btnDownloadPdf = document.getElementById("btn-download-pdf");

    btnDownload.addEventListener("click", async () => {
        if (!lastAnalysisData) return;
        showLoading("Generating HTML report...");
        await downloadFile("/api/download_report", "semantic_ir_diff_report.html");
    });
    
    btnDownloadPdf.addEventListener("click", async () => {
        if (!lastAnalysisData) return;
        showLoading("Generating PDF report...");
        await downloadFile("/api/download_pdf_report", "semantic_ir_diff_report.pdf");
    });
    
    btnExportCsv.addEventListener("click", async () => {
        if (!lastAnalysisData) return;
        showLoading("Exporting statistics to CSV...");
        const payload = { title: lastAnalysisData.title, stats: lastAnalysisData.stats };
        
        try {
            const response = await fetch("/api/export_stats", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const data = await response.json();
                showError(data.error || "Failed to export CSV", data.details || "");
                hideLoading();
                return;
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            a.download = "stats.csv";
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            hideLoading();
        } catch (err) {
            showError("Export Error", err.toString());
            hideLoading();
        }
    });

    async function downloadFile(apiEndpoint, defaultFilename) {
        const payload = getPayload();
        try {
            const response = await fetch(apiEndpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const data = await response.json();
                showError(data.error || "Failed to download", data.details || "");
                hideLoading();
                return;
            }
            
            const blob = await response.blob();
            
            // Extract filename from Content-Disposition header if available
            let filename = defaultFilename;
            const disposition = response.headers.get("Content-Disposition");
            if (disposition && disposition.indexOf("attachment") !== -1) {
                const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
                if (matches != null && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                }
            }
            
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            hideLoading();
        } catch (err) {
            showError("Download Error", err.toString());
            hideLoading();
        }
    }

    function showLoading(msg) {
        loadingMessage.textContent = msg;
        loadingOverlay.classList.remove("hidden");
    }
    
    function hideLoading() {
        loadingOverlay.classList.add("hidden");
    }
    
    function showError(msg, details) {
        errorText.textContent = msg;
        errorDetails.textContent = details;
        errorModal.classList.remove("hidden");
    }

    function renderResults(data) {
        resultsPanel.classList.remove("hidden");
        resultsPanel.scrollIntoView({ behavior: "smooth" });
        
        reportTitle.textContent = data.title;
        statCompared.textContent = data.stats.functions_compared;
        statAdded.textContent = data.stats.functions_added;
        statDeleted.textContent = data.stats.functions_deleted;
        statChanged.textContent = data.stats.functions_changed;
        statInstAdded.textContent = `+${data.stats.instructions_added}`;
        statInstDeleted.textContent = `-${data.stats.instructions_deleted}`;
        statImpact.textContent = data.stats.events_high;
        
        eventsTimeline.innerHTML = "";
        let allEvents = [];
        
        for (const [fName, func] of Object.entries(data.changed_functions)) {
            func.events.forEach(ev => {
                allEvents.push({ ...ev, functionName: fName });
            });
        }
        
        if (allEvents.length === 0) {
            eventsTimeline.innerHTML = `<div class="event-item"><p class="event-desc" style="color: var(--text-muted);">No optimization gains/losses identified. General instructional edits present.</p></div>`;
        } else {
            allEvents.forEach(ev => {
                const item = document.createElement("div");
                item.className = "event-item";
                const badgeClass = `badge-${ev.severity.toLowerCase()}`;
                
                item.innerHTML = `
                    <div class="event-info">
                        <div class="event-meta-row">
                            <span class="event-category">${ev.category}</span>
                            <span class="event-type">${ev.change_type}</span>
                            <span class="event-func">in <code>${ev.functionName}</code></span>
                        </div>
                        <p class="event-desc">${ev.description}</p>
                        ${ev.details ? `<p class="event-details"><i class="fa-solid fa-circle-chevron-right"></i> ${ev.details}</p>` : ''}
                    </div>
                    <div>
                        <span class="badge ${badgeClass}">${ev.severity}</span>
                    </div>
                `;
                
                item.style.cursor = "pointer";
                item.addEventListener("click", () => {
                    selectFunction(ev.functionName);
                });
                
                eventsTimeline.appendChild(item);
            });
        }
        
        listFunctions.innerHTML = "";
        
        data.added_functions.forEach(name => {
            const li = document.createElement("li");
            li.className = "func-item";
            li.innerHTML = `<span class="func-name">${name}</span> <span class="func-badge func-badge-added">added</span>`;
            listFunctions.appendChild(li);
        });
        
        data.deleted_functions.forEach(name => {
            const li = document.createElement("li");
            li.className = "func-item";
            li.innerHTML = `<span class="func-name">${name}</span> <span class="func-badge func-badge-deleted">deleted</span>`;
            listFunctions.appendChild(li);
        });
        
        for (const [name, func] of Object.entries(data.changed_functions)) {
            const li = document.createElement("li");
            li.className = "func-item clickable-func";
            li.setAttribute("data-func", name);
            
            // Render green or red badge based on semantic equivalence!
            const eqBadge = func.equivalent 
                ? `<span class="func-badge func-badge-added" style="font-size:0.6rem; margin-left:4px; text-transform: capitalize;">equivalent</span>`
                : `<span class="func-badge func-badge-deleted" style="font-size:0.6rem; margin-left:4px; text-transform: capitalize;">divergent</span>`;
                
            li.innerHTML = `<span class="func-name">${name}</span> <div style="display:flex; gap:3px;"><span class="func-badge func-badge-changed">changed</span>${eqBadge}</div>`;
            
            li.addEventListener("click", () => {
                selectFunction(name);
            });
            
            listFunctions.appendChild(li);
        }
        
        data.unchanged_functions.forEach(name => {
            const li = document.createElement("li");
            li.className = "func-item";
            li.innerHTML = `<span class="func-name">${name}</span> <span class="func-badge func-badge-unchanged">equal</span>`;
            listFunctions.appendChild(li);
        });
        
        const changedNames = Object.keys(data.changed_functions);
        if (changedNames.length > 0) {
            selectFunction(changedNames[0]);
        } else {
            currentFunctionName.innerHTML = `<i class="fa-solid fa-terminal"></i> No semantic changes`;
            functionMetadata.textContent = "";
            functionContentWrapper.classList.add("hidden");
            noFunctionSelected.classList.remove("hidden");
        }
    }

    async function selectFunction(name) {
        if (!lastAnalysisData) return;
        const funcData = lastAnalysisData.changed_functions[name];
        if (!funcData) return;
        
        document.querySelectorAll(".clickable-func").forEach(el => {
            if (el.getAttribute("data-func") === name) {
                el.classList.add("active");
            } else {
                el.classList.remove("active");
            }
        });
        
        noFunctionSelected.classList.add("hidden");
        functionContentWrapper.classList.remove("hidden");
        
        currentFunctionName.innerHTML = `<i class="fa-solid fa-gears"></i> Function <code>${name}</code>`;
        
        // Show semantic equivalence status in detail panel header
        const eqBadgeClass = funcData.equivalent ? 'badge-low' : 'badge-high';
        functionMetadata.innerHTML = `
            Equivalence: <span class="badge ${eqBadgeClass}">${funcData.semantic_status}</span> &nbsp;|&nbsp;
            CFG Changed: <span class="badge ${funcData.cfg_changed ? 'badge-high' : 'badge-info'}">${funcData.cfg_changed ? 'Yes' : 'No'}</span>
        `;
        
        localEventsList.innerHTML = "";
        if (funcData.events.length === 0) {
            localEventsList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.85rem;">No high-level compiler optimization actions identified inside this function (just instructional replacements).</p>`;
        } else {
            funcData.events.forEach(ev => {
                const div = document.createElement("div");
                div.className = "event-item";
                div.style.marginBottom = "8px";
                div.style.padding = "10px 14px";
                div.style.background = "rgba(255, 255, 255, 0.02)";
                
                const badgeClass = `badge-${ev.severity.toLowerCase()}`;
                
                div.innerHTML = `
                    <div class="event-info">
                        <div class="event-meta-row">
                            <span class="event-category" style="font-size:0.75rem;">${ev.category}</span>
                            <span class="event-type" style="font-size:0.65rem;">${ev.change_type}</span>
                        </div>
                        <p class="event-desc" style="font-size:0.85rem;">${ev.description}</p>
                        ${ev.details ? `<p class="event-details" style="font-size:0.75rem;"><i class="fa-solid fa-angles-right"></i> ${ev.details}</p>` : ''}
                    </div>
                    <div>
                        <span class="badge ${badgeClass}" style="font-size:0.65rem;">${ev.severity}</span>
                    </div>
                `;
                localEventsList.appendChild(div);
            });
        }
        
        renderBlockSplitDiffs(funcData);
        await renderCFGs(funcData);
    }

    function renderBlockSplitDiffs(funcData) {
        blockDiffsContainer.innerHTML = "";
        
        funcData.old_block_order.forEach(o_lbl => {
            if (!(o_lbl in funcData.matched_blocks)) {
                const oldBlockData = funcData.old_blocks[o_lbl];
                const card = document.createElement("div");
                card.className = "block-diff-card";
                card.id = `diff-block-${o_lbl}`;
                
                let tbody = "";
                oldBlockData.instructions.forEach(inst => {
                    tbody += `<tr><td class="code-col deleted-line">${inst}</td><td class="code-col empty-line"></td></tr>`;
                });
                
                card.innerHTML = `
                    <h5 style="border-top: 3px solid var(--color-rose);"><i class="fa-solid fa-trash-can color-deleted"></i> Deleted Block: <code>{o_lbl}</code></h5>
                    <table class="split-diff-table">
                        <thead>
                            <tr><th>Original</th><th>Modified</th></tr>
                        </thead>
                        <tbody>${tbody}</tbody>
                    </table>
                `;
                blockDiffsContainer.appendChild(card);
                return;
            }
            
            const b_diff = funcData.matched_blocks[o_lbl];
            if (b_diff.is_identical) return;
            
            const card = document.createElement("div");
            card.className = "block-diff-card";
            card.id = `diff-block-${o_lbl}`;
            
            let tbody = "";
            b_diff.diff_lines.forEach(([marker, line]) => {
                if (marker === '-') {
                    tbody += `<tr><td class="code-col deleted-line">- ${line}</td><td class="code-col empty-line"></td></tr>`;
                } else if (marker === '+') {
                    tbody += `<tr><td class="code-col empty-line"></td><td class="code-col added-line">+ ${line}</td></tr>`;
                } else {
                    tbody += `<tr><td class="code-col unchanged-line">  ${line}</td><td class="code-col unchanged-line">  ${line}</td></tr>`;
                }
            });
            
            card.innerHTML = `
                <h5 style="border-top: 3px solid var(--color-amber);"><i class="fa-solid fa-pen-to-square" style="color:var(--color-amber);"></i> Changed Block: <code>${o_lbl}</code> &rarr; <code>${b_diff.new_label}</code></h5>
                <table class="split-diff-table">
                    <thead>
                        <tr><th>Original ${o_lbl}</th><th>Modified ${b_diff.new_label}</th></tr>
                    </thead>
                    <tbody>${tbody}</tbody>
                </table>
            `;
            blockDiffsContainer.appendChild(card);
        });
        
        funcData.added_blocks.forEach(n_lbl => {
            const newBlockData = funcData.new_blocks[n_lbl];
            const card = document.createElement("div");
            card.className = "block-diff-card";
            card.id = `diff-block-${n_lbl}`;
            
            let tbody = "";
            newBlockData.instructions.forEach(inst => {
                tbody += `<tr><td class="code-col empty-line"></td><td class="code-col added-line">+ ${inst}</td></tr>`;
            });
            
            card.innerHTML = `
                <h5 style="border-top: 3px solid var(--color-emerald);"><i class="fa-solid fa-folder-plus color-added"></i> Added Block: <code>${n_lbl}</code></h5>
                <table class="split-diff-table">
                    <thead>
                        <tr><th>Original</th><th>Modified</th></tr>
                    </thead>
                    <tbody>${tbody}</tbody>
                </table>
            `;
            blockDiffsContainer.appendChild(card);
        });
        
        if (blockDiffsContainer.children.length === 0) {
            blockDiffsContainer.innerHTML = `<div class="block-diff-card" style="padding: 16px; color: var(--text-muted); font-size: 0.85rem; text-align: center;"><i class="fa-solid fa-equals"></i> No instruction differences in any of the matched basic blocks.</div>`;
        }
    }

    function buildMermaidCFG(blocks, matchedBlocks, isNew = false, addedBlocks = [], deletedBlocks = []) {
        let lines = ["graph TD"];
        
        lines.push("classDef default fill:#090d16,stroke:#2d3748,stroke-width:1px,color:#cbd5e1;");
        lines.push("classDef added fill:#052e16,stroke:#10b981,stroke-width:2px,color:#d1fae5;");
        lines.push("classDef deleted fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#fee2e2;");
        lines.push("classDef changed fill:#451a03,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;");
        
        for (const [lbl, block] of Object.entries(blocks)) {
            const instCount = block.instructions.length;
            const labelText = `<b>${lbl}</b><br/>(${instCount} instructions)`;
            
            let styleClass = "";
            if (isNew && addedBlocks.includes(lbl)) {
                styleClass = ":::added";
            } else if (!isNew && deletedBlocks.includes(lbl)) {
                styleClass = ":::deleted";
            } else {
                const matchedLbl = isNew ? Object.keys(matchedBlocks).find(k => matchedBlocks[k].new_label === lbl) : lbl;
                if (matchedLbl) {
                    const diff = isNew ? matchedBlocks[matchedLbl] : matchedBlocks[lbl];
                    if (diff && !diff.is_identical) {
                        styleClass = ":::changed";
                    }
                }
            }
            
            lines.push(`    ${lbl}["${labelText}"]${styleClass}`);
            
            block.successors.forEach(succ => {
                lines.push(`    ${lbl} --> ${succ}`);
            });
        }
        
        return lines.join("\n");
    }

    async function renderCFGs(funcData) {
        cfgGraphOld.innerHTML = "<div class='spinner' style='width:20px; height:20px; border-width:2px;'></div>";
        cfgGraphNew.innerHTML = "<div class='spinner' style='width:20px; height:20px; border-width:2px;'></div>";
        
        const oldMermaidDef = buildMermaidCFG(funcData.old_blocks, funcData.matched_blocks, false, [], funcData.deleted_blocks);
        const newMermaidDef = buildMermaidCFG(funcData.new_blocks, funcData.matched_blocks, true, funcData.added_blocks, []);
        
        try {
            const oldId = `svg-old-${Math.random().toString(36).substring(2, 9)}`;
            const newId = `svg-new-${Math.random().toString(36).substring(2, 9)}`;
            
            const m = window.mermaid;
            if (!m) {
                throw new Error("Mermaid.js is not yet initialized on the page.");
            }
            
            const { svg: oldSvg, bindFunctions: oldBind } = await m.render(oldId, oldMermaidDef);
            cfgGraphOld.innerHTML = oldSvg;
            oldBind?.(cfgGraphOld);
            
            const { svg: newSvg, bindFunctions: newBind } = await m.render(newId, newMermaidDef);
            cfgGraphNew.innerHTML = newSvg;
            newBind?.(cfgGraphNew);
            
            setupGraphNodeInteractivity(cfgGraphOld, funcData.matched_blocks);
            setupGraphNodeInteractivity(cfgGraphNew, funcData.matched_blocks);
            
        } catch (err) {
            console.error("Mermaid render error:", err);
            cfgGraphOld.innerHTML = `<span style='color:var(--color-rose); font-size:0.8rem;'>Graph render error</span>`;
            cfgGraphNew.innerHTML = `<span style='color:var(--color-rose); font-size:0.8rem;'>Graph render error</span>`;
        }
    }

    function setupGraphNodeInteractivity(container, matchedBlocks) {
        const nodes = container.querySelectorAll(".node");
        nodes.forEach(node => {
            node.addEventListener("click", () => {
                const nodeId = node.id.split("-")[1];
                if (!nodeId) return;
                
                const matchedMatch = nodeId.match(/^(block_\d+)/);
                if (!matchedMatch) return;
                const blockLabel = matchedMatch[1];
                
                let oldLabel = blockLabel;
                const foundKey = Object.keys(matchedBlocks).find(k => matchedBlocks[k].new_label === blockLabel);
                if (foundKey) {
                    oldLabel = foundKey;
                }
                
                const targetCard = document.getElementById(`diff-block-${oldLabel}`) || document.getElementById(`diff-block-${blockLabel}`);
                if (targetCard) {
                    document.querySelectorAll(".block-diff-card").forEach(c => c.classList.remove("highlighted"));
                    targetCard.classList.add("highlighted");
                    targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            });
        });
    }
});
