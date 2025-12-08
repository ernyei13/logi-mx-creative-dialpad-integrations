/**
 * Logi Receiver - ExtendScript for After Effects
 * Controls any effect property on the currently selected layer via Logi dial
 * * Usage: File > Scripts > Run Script File... and select this file
 * * The Python server writes accumulated position to C:/temp/logi_position.json
 * This script reads that file and updates the selected effect property!
 */

// Simple JSON parser for ExtendScript (which doesn't have native JSON)
if (typeof JSON === 'undefined') {
    JSON = {
        parse: function(str) {
            return eval('(' + str + ')');
        },
        stringify: function(obj) {
            var t = typeof obj;
            if (t !== "object" || obj === null) {
                if (t === "string") return '"' + obj + '"';
                return String(obj);
            }
            var n, v, json = [], arr = (obj && obj.constructor === Array);
            for (n in obj) {
                v = obj[n];
                t = typeof v;
                if (t === "string") v = '"' + v + '"';
                else if (t === "object" && v !== null) v = JSON.stringify(v);
                json.push((arr ? "" : '"' + n + '":') + String(v));
            }
            return (arr ? "[" : "{") + String(json) + (arr ? "]" : "}");
        }
    };
}

(function(thisObj) {
    var POSITION_FILE = "C:/temp/logi_position.json";
    var BUTTON_FILE = "C:/temp/logi_button.json";
    
    // Calculate script path first (used for repo fallback candidate)
    var scriptFile = new File($.fileName);
    var parentFolder = scriptFile.parent.fsName;
    var SCRIPT_PATH = parentFolder + "\\logi-mx-creative-dialpad-integrations";

    // Fallback candidate folders (will try in order)
    var fallbackCandidates = [];
    try {
        if ($.getenv) {
            var envTemp = $.getenv("TEMP");
            if (envTemp) fallbackCandidates.push(envTemp.replace(/\\/g, "/"));
        }
    } catch (e) {}
    // Add common locations
    fallbackCandidates.push("C:/temp");
    // Repo example temps (relative to script file)
    try {
        var repoExample = scriptFile.parent.fsName + "/../example_temps";
        fallbackCandidates.push(repoExample);
    } catch (e) {}
    // Normalize candidates
    for (var _i = 0; _i < fallbackCandidates.length; _i++) {
        fallbackCandidates[_i] = fallbackCandidates[_i].replace(/\\\\/g, "/");
    }
    
    
    // State
    var isActive = false;
    var autoUpdateInterval = null;
    var lastDialValue = null;
    var lastSmallDialValue = null;  // Track small dial separately
    var lastLayerName = "";
    var currentEffects = [];
    var currentProperties = [];
    var lastButtonTimestamp = 0;  // Track button events to avoid duplicates
    var mappingsCache = {};  // In-memory cache: { "EffectName": { buttons: {...} }, ... }
    var isLoadingMappings = false;  // Flag to prevent auto-save while loading
    // Debug traces
    var lastRawPositionContent = "";
    var lastRawButtonContent = "";
    var verboseDebug = false;
    var lastPositionTS = 0;
    
    // Build UI - support both dockable panel and floating window
    function buildUI(thisObj) {
        var win = (thisObj instanceof Panel) ? thisObj : new Window("palette", "Logi Dial - Effect Control", undefined, {resizeable: true});
        return win;
    }
    
    var win = buildUI(thisObj);
    win.orientation = "row";
    win.alignChildren = ["fill", "fill"];
    win.spacing = 0;
    win.margins = 4;
    
    // Main content group (will be scrolled)
    var contentGroup = win.add("group");
    contentGroup.orientation = "column";
    contentGroup.alignChildren = ["fill", "top"];
    contentGroup.alignment = ["fill", "fill"];
    contentGroup.spacing = 4;
    
    // Scrollbar
    var scrollbar = win.add("scrollbar", undefined, 0, 0, 100);
    scrollbar.preferredSize = [16, -1];
    scrollbar.alignment = ["right", "fill"];
    
    // Inner content container that moves up/down
    var scrollContent = contentGroup.add("group");
    scrollContent.orientation = "column";
    scrollContent.alignChildren = ["fill", "top"];
    scrollContent.alignment = ["fill", "top"];
    scrollContent.spacing = 4;
    
    // Status
    var statusPanel = scrollContent.add("panel", undefined, "Status");
    statusPanel.alignChildren = ["fill", "top"];
    var statusText = statusPanel.add("statictext", undefined, "Select a layer to see its effects");
    statusText.characters = 50;
    
    // Current layer display
    var layerText = statusPanel.add("statictext", undefined, "Selected: (none)");
    layerText.characters = 45;
    
    // Live value display
    var valDisplayGroup = statusPanel.add("group");
    valDisplayGroup.orientation = "row";
    valDisplayGroup.add("statictext", undefined, "Value:");
    var valDisplay = valDisplayGroup.add("statictext", undefined, "---");
    valDisplay.characters = 15;

    // Heartbeat display to confirm scheduled polling is running
    var heartbeatText = statusPanel.add("statictext", undefined, "HB: n/a");
    heartbeatText.characters = 30;

    // Debug display (collapsed unless verbose enabled)
    var debugGroup = statusPanel.add("group");
    debugGroup.orientation = "column";
    debugGroup.alignment = ["fill", "top"];
    var verboseCb = debugGroup.add("checkbox", undefined, "Verbose Debug");
    verboseCb.value = false;
    var posExistsText = debugGroup.add("statictext", undefined, "pos file: (unknown)");
    var posRawText = debugGroup.add("statictext", undefined, "pos raw: ");
    posRawText.characters = 60;
    var btnExistsText = debugGroup.add("statictext", undefined, "btn file: (unknown)");
    var btnRawText = debugGroup.add("statictext", undefined, "btn raw: ");
    btnRawText.characters = 60;
    verboseCb.onClick = function() {
        verboseDebug = verboseCb.value;
        posExistsText.visible = verboseDebug;
        posRawText.visible = verboseDebug;
        btnExistsText.visible = verboseDebug;
        btnRawText.visible = verboseDebug;
    };
    // Start hidden
    posExistsText.visible = false;
    posRawText.visible = false;
    btnExistsText.visible = false;
    btnRawText.visible = false;
    // Manual read button to force reading files and show results
    var manualReadBtn = debugGroup.add("button", undefined, "Read Now");
    manualReadBtn.onClick = function() {
        // Force a read and update UI
        try { readPositionFile(); } catch (e) {}
        try { readButtonFile(); } catch (e) {}
        posExistsText.text = "pos file: " + ((lastRawPositionContent && lastRawPositionContent.length > 0) ? "present" : "(empty)");
        posRawText.text = "pos raw: " + (lastRawPositionContent || "");
        btnExistsText.text = "btn file: " + ((lastRawButtonContent && lastRawButtonContent.length > 0) ? "present" : "(empty)");
        btnRawText.text = "btn raw: " + (lastRawButtonContent || "");
        posExistsText.visible = true;
        posRawText.visible = true;
        btnExistsText.visible = true;
        btnRawText.visible = true;
        alert("Read Now:\npos=> " + (lastRawPositionContent || "(empty)") + "\nbtn=> " + (lastRawButtonContent || "(empty)"));
    };
    
    // Effect/Property Selection
    var targetPanel = scrollContent.add("panel", undefined, "Target Effect & Property");
    targetPanel.alignChildren = ["fill", "top"];
    
    // Effect dropdown
    var effectGroup = targetPanel.add("group");
    effectGroup.add("statictext", undefined, "Effect:");
    var effectDropdown = effectGroup.add("dropdownlist", undefined, ["(select layer first)"]);
    effectDropdown.preferredSize = [250, 25];
    effectDropdown.selection = 0;
    
    // Property dropdown
    var propGroup = targetPanel.add("group");
    propGroup.add("statictext", undefined, "Property:");
    var propDropdown = propGroup.add("dropdownlist", undefined, ["(select effect first)"]);
    propDropdown.preferredSize = [250, 25];
    propDropdown.selection = 0;
    
    // Refresh button
    var refreshBtn = targetPanel.add("button", undefined, "Refresh Effects List");
    var debugBtn = targetPanel.add("button", undefined, "Debug: List ALL Properties");
    
    // Sensitivity
    var sensPanel = scrollContent.add("panel", undefined, "Settings");
    sensPanel.alignChildren = ["fill", "top"];
    
    var sensGroup = sensPanel.add("group");
    sensGroup.add("statictext", undefined, "Big Dial:");
    var sensInput = sensGroup.add("edittext", undefined, "0.1");
    sensInput.characters = 8;
    sensGroup.add("statictext", undefined, "(property)");
    
    var sensGroup2 = sensPanel.add("group");
    sensGroup2.add("statictext", undefined, "Small Dial:");
    var sensInputTimeline = sensGroup2.add("edittext", undefined, "1");
    sensInputTimeline.characters = 8;
    sensGroup2.add("statictext", undefined, "(frames)");
    
    // Keypad Mapping Panel
    var keypadPanel = scrollContent.add("panel", undefined, "Keypad Button Mapping");
    keypadPanel.alignChildren = ["fill", "top"];
    
    // Button mapping dropdowns - 9 buttons on the keypad (3x3 grid)
    // Buttons 1-6 are for property mapping
    // Buttons 7-8-9 are special: 7=prev keyframe, 8=add keyframe, 9=next keyframe
    var keypadButtons = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
    var keypadDropdowns = [];
    var keypadMappings = {}; // Maps button name to property index
    
    // Create first 2 rows (buttons 1-6) with dropdowns for property mapping
    for (var row = 0; row < 2; row++) {
        var rowGroup = keypadPanel.add("group");
        rowGroup.orientation = "row";
        rowGroup.alignChildren = ["left", "center"];
        
        for (var col = 0; col < 3; col++) {
            var btnIdx = row * 3 + col;
            var btnName = keypadButtons[btnIdx];
            
            var btnGroup = rowGroup.add("group");
            btnGroup.orientation = "row";
            btnGroup.add("statictext", undefined, "[" + btnName + "]");
            
            var dropdown = btnGroup.add("dropdownlist", undefined, ["(none)"]);
            dropdown.preferredSize = [120, 22];
            dropdown.selection = 0;
            dropdown.buttonName = btnName; // Store button name for reference
            
            keypadDropdowns.push(dropdown);
        }
    }
    
    // Row 3: Special keyframe buttons (7, 8, 9) - just labels, no dropdowns
    var specialRowGroup = keypadPanel.add("group");
    specialRowGroup.orientation = "row";
    specialRowGroup.alignChildren = ["left", "center"];
    specialRowGroup.add("statictext", undefined, "[7] Prev KF");
    specialRowGroup.add("statictext", undefined, "   [8] Add KF");
    specialRowGroup.add("statictext", undefined, "   [9] Next KF");
    
    // Save/Load mapping buttons
    var mappingBtnGroup = keypadPanel.add("group");
    mappingBtnGroup.orientation = "row";
    var saveMappingBtn = mappingBtnGroup.add("button", undefined, "Save Mapping");
    var loadMappingBtn = mappingBtnGroup.add("button", undefined, "Load Mapping");
    
    // Host mode panel
    var hostPanel = scrollContent.add("panel", undefined, "Host Mode");
    hostPanel.alignChildren = ["fill", "top"];
    
    // Remote host checkbox - if enabled, only start webserver (not host.py)
    var remoteHostCb = hostPanel.add("checkbox", undefined, "Remote Host (host.py runs elsewhere)");
    remoteHostCb.value = false;
    
    // Buttons
    var buttonPanel = scrollContent.add("panel", undefined, "Controls");
    buttonPanel.alignChildren = ["fill", "top"];
    
    var btnGroup1 = buttonPanel.add("group");
    var startBtn = btnGroup1.add("button", undefined, "Start");
    var stopBtn = btnGroup1.add("button", undefined, "Stop");
    stopBtn.enabled = false;
    
    var btnGroup2 = buttonPanel.add("group");
    var resetBtn = btnGroup2.add("button", undefined, "Reset Dial");
    var debugPathBtn = btnGroup2.add("button", undefined, "Debug Path");
    
    // Debug button to show the path being used
    debugPathBtn.onClick = function() {
        alert("Script File:\n" + $.fileName + "\n\nCalculated Integration Path:\n" + SCRIPT_PATH);
    };
    
    // Cache for last valid position (prevents glitches from corrupted reads)
    var lastValidPosition = {x: 0, y: 0};
    
    /**
     * Run a batch file - simple execute() method
     */
    function runBatchFile(batPath) {
        var batFile = new File(batPath);
        
        // Debug: show exactly what we're trying to run
        alert("Attempting to run:\n" + batFile.fsName + "\n\nExists: " + batFile.exists);
        
        if (!batFile.exists) 
            return false;
        
        
        // Execute directly - this opens the file as if you double-clicked it
        var result = batFile.execute();
        alert("Execute returned: " + result);
        return result;
    }
    
    /**
     * Start the host.py and web_server.py in background (headless)
     * Updated to use the DEBUG batch file as requested
     */
    function startHostServices() {
        return runBatchFile(SCRIPT_PATH + "\\start_logi_host_debug.bat");
    }
    
    /**
     * Start only the web_server.py (for remote host mode, headless)
     */
    function startWebServerOnly() {
        return runBatchFile("C:\\Program Files\Adobe\Adobe After Effects 2025\Support Files\Scripts\ScriptUI Panels\logi-mx-creative-dialpad-integrations\start_webserver_debug.bat");
    }
    
    /**
     * Stop the host.py and web_server.py processes
     * Uses taskkill directly via system.callSystem
     */
    function stopHostServices() {
        try {
            // Kill python processes running web_server.py
            system.callSystem('taskkill /F /FI "WINDOWTITLE eq Logi Web Server*"');
            system.callSystem('taskkill /F /FI "WINDOWTITLE eq Logi Host*"');
            // Kill by image name and command line pattern
            system.callSystem('cmd /c "FOR /F \\"tokens=2 delims=,\\" %i IN (\'tasklist /FI \\"IMAGENAME eq python.exe\\" /FO CSV /NH\') DO @wmic process where \\"ProcessId=%~i and CommandLine like \'%%web_server.py%%\'\\" call terminate >nul 2>&1"');
            return true;
        } catch (e) {
            // Fallback: try running the batch file
            var batPath = "C:\\Program Files\\Adobe\\Adobe After Effects 2025\\Support Files\\Scripts\\ScriptUI Panels\\logi-mx-creative-dialpad-integrations\\stop_logi_host.bat";
            var batFile = new File(batPath);
            if (batFile.exists) {
                batFile.execute();
            }
            return false;
        }
    }
    
    /**
     * Read position from file with validation
     * Returns cached value if read fails or data is invalid
     */
    function readPositionFile() {
        // Try primary path first, then fallbacks
        lastRawPositionContent = "";
        var triedPaths = [];
        try {
            var tryPath = function(path) {
                triedPaths.push(path);
                try {
                    var f = new File(path);
                    if (!f.exists) return null;
                    f.open('r');
                    var c = f.read();
                    f.close();
                    lastRawPositionContent = c;
                    if (c && c.length > 0) {
                        c = c.replace(/^\s+|\s+$/g, '');
                        if (c.charAt(0) !== '{' || c.charAt(c.length - 1) !== '}') return null;
                            var parsed = JSON.parse(c);
                            // Check timestamp to avoid reprocessing identical file contents
                            var ts = (parsed && (parsed._ts || parsed.timestamp)) || 0;
                            if (ts && ts === lastPositionTS) {
                                return lastValidPosition; // unchanged
                            }
                            if (ts) lastPositionTS = ts;
                            if (typeof parsed.x === 'number' && typeof parsed.y === 'number' && isFinite(parsed.x) && isFinite(parsed.y)) {
                                lastValidPosition = parsed;
                                return parsed;
                            }
                    }
                } catch (e) {}
                return null;
            };

            // Primary
            var res = tryPath(POSITION_FILE);
            if (res) return res;

            // Try fallbacks
            for (var i = 0; i < fallbackCandidates.length; i++) {
                var candidate = fallbackCandidates[i];
                if (!candidate) continue;
                var p = candidate.replace(/\/$/, '') + '/logi_position.json';
                res = tryPath(p);
                if (res) return res;
            }

            // If not found, mark missing
            if (!lastRawPositionContent) lastRawPositionContent = '(missing)';
        } catch (e) {}
        return lastValidPosition;
    }
    
    /**
     * Read button state from file
     * Returns {button: "TOP LEFT", pressed: true, timestamp: 123456} or null
     */
    function readButtonFile() {
        // Try primary path then fallbacks
        lastRawButtonContent = "";
        try {
            var tryPathB = function(path) {
                try {
                    var f = new File(path);
                    if (!f.exists) return null;
                    f.open('r');
                    var c = f.read();
                    f.close();
                    lastRawButtonContent = c;
                    if (c && c.length > 0) {
                        c = c.replace(/^\s+|\s+$/g, '');
                        if (c.charAt(0) === '{' && c.charAt(c.length - 1) === '}') {
                            try { return JSON.parse(c); } catch (e) { return null; }
                        }
                    }
                } catch (e) {}
                return null;
            };

            var r = tryPathB(BUTTON_FILE);
            if (r) return r;
            for (var j = 0; j < fallbackCandidates.length; j++) {
                var cand = fallbackCandidates[j];
                if (!cand) continue;
                var pb = cand.replace(/\/$/, '') + '/logi_button.json';
                r = tryPathB(pb);
                if (r) return r;
            }
            if (!lastRawButtonContent) lastRawButtonContent = '(missing)';
        } catch (e) {}
        return null;
    }
    
    /**
     * Get all effects on a layer
     */
    function getLayerEffects(layer) {
        var effects = [];
        try {
            var effectsGroup = layer.property("ADBE Effect Parade");
            if (effectsGroup) {
                for (var i = 1; i <= effectsGroup.numProperties; i++) {
                    var effect = effectsGroup.property(i);
                    effects.push({
                        name: effect.name,
                        index: i,
                        effect: effect
                    });
                }
            }
        } catch (e) {}
        return effects;
    }
    
    /**
     * Get all properties of an effect (including nested groups)
     * Lists ALL properties so user can try any parameter
     */
    function getEffectProperties(effect, prefix) {
        var props = [];
        prefix = prefix || "";
        
        try {
            for (var i = 1; i <= effect.numProperties; i++) {
                var prop;
                try {
                    prop = effect.property(i);
                } catch (e) {
                    continue; // Skip properties that can't be accessed
                }
                
                if (!prop) continue;
                
                // Get property name - use matchName if name is empty
                var displayName = prop.name;
                if (!displayName || displayName === "") {
                    displayName = "[" + prop.matchName + "]";
                }
                var propName = prefix ? (prefix + " > " + displayName) : displayName;
                
                // Get property type safely
                var propType = null;
                try {
                    propType = prop.propertyType;
                } catch (e) {}
                
                // If it's a property group, recurse into it
                if (propType === PropertyType.INDEXED_GROUP || 
                    propType === PropertyType.NAMED_GROUP) {
                    var nestedProps = getEffectProperties(prop, propName);
                    for (var j = 0; j < nestedProps.length; j++) {
                        props.push(nestedProps[j]);
                    }
                }
                // Include ALL properties
                else {
                    var valueType = null;
                    var currentValue = null;
                    var hasNumericValue = false;
                    
                    try {
                        valueType = prop.propertyValueType;
                    } catch (e) {}
                    
                    try {
                        currentValue = prop.value;
                        // Check if it's a usable numeric value
                        if (typeof currentValue === "number") {
                            hasNumericValue = true;
                        } else if (currentValue instanceof Array && currentValue.length > 0 && typeof currentValue[0] === "number") {
                            hasNumericValue = true;
                        }
                    } catch (e) {}
                    
                    // Only add properties that have readable numeric values
                    if (hasNumericValue) {
                        props.push({
                            name: propName,
                            index: i,
                            prop: prop,
                            valueType: valueType,
                            currentValue: currentValue,
                            matchName: prop.matchName
                        });
                    }
                }
            }
        } catch (e) {}
        return props;
    }
    
    /**
     * Populate effect dropdown for selected layer
     */
    function populateEffects() {
        // Clear dropdowns
        effectDropdown.removeAll();
        propDropdown.removeAll();
        currentEffects = [];
        currentProperties = [];
        
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) {
                effectDropdown.add("item", "(no composition)");
                effectDropdown.selection = 0;
                return;
            }
            
            var layer = comp.selectedLayers[0];
            if (!layer) {
                effectDropdown.add("item", "(no layer selected)");
                effectDropdown.selection = 0;
                return;
            }
            
            layerText.text = "Selected: " + layer.name;
            
            currentEffects = getLayerEffects(layer);
            
            if (currentEffects.length === 0) {
                effectDropdown.add("item", "(no effects on layer)");
                effectDropdown.selection = 0;
                propDropdown.add("item", "(select effect first)");
                propDropdown.selection = 0;
                return;
            }
            
            for (var i = 0; i < currentEffects.length; i++) {
                effectDropdown.add("item", currentEffects[i].name);
            }
            effectDropdown.selection = 0;
            
            // Populate properties for first effect
            populateProperties();
            updateKeypadDropdowns();
            autoLoadMappings(); // Restore saved mappings for this effect
            
        } catch (e) {
            statusText.text = "Error: " + e.message;
        }
    }
    
    /**
     * Populate property dropdown for selected effect
     */
    function populateProperties() {
        propDropdown.removeAll();
        currentProperties = [];
        
        var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
        if (effectIdx < 0 || effectIdx >= currentEffects.length) {
            propDropdown.add("item", "(select effect first)");
            propDropdown.selection = 0;
            return;
        }
        
        var effect = currentEffects[effectIdx].effect;
        currentProperties = getEffectProperties(effect);
        
        if (currentProperties.length === 0) {
            propDropdown.add("item", "(no adjustable properties)");
            propDropdown.selection = 0;
            statusText.text = "No numeric properties found in this effect";
            return;
        }
        
        statusText.text = "Found " + currentProperties.length + " properties";
        
        for (var i = 0; i < currentProperties.length; i++) {
            var p = currentProperties[i];
            // Just use the property name without values
            propDropdown.add("item", p.name);
        }
        propDropdown.selection = 0;
    }
    
    /**
     * Update keypad button dropdowns with current properties
     */
    function updateKeypadDropdowns() {
        isLoadingMappings = true;  // Prevent auto-save during update
        
        for (var i = 0; i < keypadDropdowns.length; i++) {
            var dropdown = keypadDropdowns[i];
            var currentSelection = dropdown.selection ? dropdown.selection.index : 0;
            
            dropdown.removeAll();
            dropdown.add("item", "(none)");
            
            for (var j = 0; j < currentProperties.length; j++) {
                dropdown.add("item", currentProperties[j].name);
            }
            
            // Restore selection if valid
            if (currentSelection > 0 && currentSelection <= currentProperties.length) {
                dropdown.selection = currentSelection;
            } else {
                dropdown.selection = 0;
            }
        }
        
        isLoadingMappings = false;  // Re-enable auto-save
    }
    
    // Mappings folder path
    var MAPPINGS_FOLDER = "C:/Program Files/Adobe/Adobe After Effects 2025/Support Files/Scripts/ScriptUI Panels/logi-mx-creative-dialpad-integrations/mappings";
    
    /**
     * Ensure mappings folder exists
     */
    function ensureMappingsFolder() {
        var folder = new Folder(MAPPINGS_FOLDER);
        if (!folder.exists) {
            folder.create();
        }
    }
    
    /**
     * Get a safe filename for an effect (remove special characters)
     */
    function getEffectFileName(effectName) {
        return effectName.replace(/[^a-zA-Z0-9]/g, "_") + ".json";
    }
    
    /**
     * Auto-save current mappings to JSON file and in-memory cache
     */
    function autoSaveMappings() {
        // Don't save if we're currently loading mappings (programmatic changes)
        if (isLoadingMappings) return;
        
        try {
            var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
            if (effectIdx < 0 || effectIdx >= currentEffects.length) return;
            
            var effectName = currentEffects[effectIdx].name;
            var fileName = getEffectFileName(effectName);
            
            var mappings = {
                effectName: effectName,
                buttons: {}
            };
            
            for (var i = 0; i < keypadDropdowns.length; i++) {
                var dropdown = keypadDropdowns[i];
                var btnName = keypadButtons[i];
                var propIdx = dropdown.selection ? dropdown.selection.index : 0;
                
                if (propIdx > 0 && propIdx <= currentProperties.length) {
                    mappings.buttons[btnName] = currentProperties[propIdx - 1].name;
                }
            }
            
            // Save to in-memory cache
            mappingsCache[effectName] = mappings;
            
            // Save to file
            ensureMappingsFolder();
            var saveFile = new File(MAPPINGS_FOLDER + "/" + fileName);
            saveFile.open("w");
            saveFile.write(JSON.stringify(mappings));
            saveFile.close();
        } catch (e) {}
    }
    
    /**
     * Auto-load mappings from cache first, then JSON file for current effect
     */
    function autoLoadMappings() {
        isLoadingMappings = true;  // Prevent auto-save during loading
        
        try {
            var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
            if (effectIdx < 0 || effectIdx >= currentEffects.length) {
                isLoadingMappings = false;
                return;
            }
            
            var effectName = currentEffects[effectIdx].name;
            var mappings = null;
            
            // First check in-memory cache
            if (mappingsCache[effectName]) {
                mappings = mappingsCache[effectName];
            } else {
                // Load from file if not in cache
                var fileName = getEffectFileName(effectName);
                var loadFile = new File(MAPPINGS_FOLDER + "/" + fileName);
                if (loadFile.exists) {
                    loadFile.open("r");
                    var content = loadFile.read();
                    loadFile.close();
                    mappings = JSON.parse(content);
                    // Store in cache for future use
                    mappingsCache[effectName] = mappings;
                }
            }
            
            if (!mappings) {
                isLoadingMappings = false;
                return;
            }
            
            // Apply mappings to dropdowns
            for (var i = 0; i < keypadDropdowns.length; i++) {
                var dropdown = keypadDropdowns[i];
                var btnName = keypadButtons[i];
                
                if (mappings.buttons && mappings.buttons[btnName]) {
                    var propName = mappings.buttons[btnName];
                    
                    // Find matching property by name
                    var found = false;
                    for (var j = 0; j < currentProperties.length; j++) {
                        if (currentProperties[j].name === propName) {
                            dropdown.selection = j + 1;
                            found = true;
                            break;
                        }
                    }
                    
                    if (!found) {
                        dropdown.selection = 0;
                    }
                } else {
                    dropdown.selection = 0;
                }
            }
            
            statusText.text = "Loaded mapping for: " + effectName;
        } catch (e) {}
        
        isLoadingMappings = false;  // Re-enable auto-save
    }
    
    /**
     * Save keypad mappings to a JSON file (manual export)
     */
    function saveKeypadMappings() {
        var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
        if (effectIdx < 0 || effectIdx >= currentEffects.length) {
            alert("No effect selected");
            return;
        }
        
        // Just call autoSave which saves to the mappings folder
        autoSaveMappings();
        statusText.text = "Mapping saved for: " + currentEffects[effectIdx].name;
    }
    
    /**
     * Load keypad mappings from the mappings folder (shows file picker in that folder)
     */
    function loadKeypadMappings() {
        ensureMappingsFolder();
        var folder = new Folder(MAPPINGS_FOLDER);
        var loadFile = File.openDialog("Load Keypad Mapping", "JSON Files:*.json", false);
        if (!loadFile) return;
        
        try {
            loadFile.open("r");
            var content = loadFile.read();
            loadFile.close();
            
            var mappings = JSON.parse(content);
            
            // Apply mappings to dropdowns (only buttons 1-6)
            for (var i = 0; i < keypadDropdowns.length; i++) {
                var dropdown = keypadDropdowns[i];
                var btnName = keypadButtons[i];
                
                // Handle both old format (with propertyName) and new format (direct name)
                var propName = null;
                if (mappings.buttons && mappings.buttons[btnName]) {
                    if (typeof mappings.buttons[btnName] === "string") {
                        propName = mappings.buttons[btnName];
                    } else if (mappings.buttons[btnName].propertyName) {
                        propName = mappings.buttons[btnName].propertyName;
                    }
                }
                
                if (propName) {
                    // Find matching property by name
                    var found = false;
                    for (var j = 0; j < currentProperties.length; j++) {
                        if (currentProperties[j].name === propName) {
                            dropdown.selection = j + 1;
                            found = true;
                            break;
                        }
                    }
                    
                    if (!found) {
                        dropdown.selection = 0;
                    }
                } else {
                    dropdown.selection = 0;
                }
            }
            
            // Also save to the auto-save location
            autoSaveMappings();
            
            statusText.text = "Mapping loaded: " + (mappings.effectName || "Unknown effect");
        } catch (e) {
            alert("Error loading mapping: " + e.message);
        }
    }
    
    // Auto-save when dropdown selection changes
    for (var i = 0; i < keypadDropdowns.length; i++) {
        keypadDropdowns[i].onChange = function() {
            autoSaveMappings();
        };
    }
    
    // Save/Load button handlers
    saveMappingBtn.onClick = saveKeypadMappings;
    loadMappingBtn.onClick = loadKeypadMappings;
    
    // Effect dropdown change handler
    effectDropdown.onChange = function() {
        populateProperties();
        updateKeypadDropdowns();
        autoLoadMappings(); // Load saved mappings for this effect
        lastDialValue = null;
    };
    
    // Property dropdown change handler  
    propDropdown.onChange = function() {
        lastDialValue = null;
    };
    
    /**
     * Select a layer by index in the current comp
     */
    function selectLayerByIndex(layerIndex) {
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) return;
            
            if (layerIndex >= 1 && layerIndex <= comp.numLayers) {
                // Deselect all layers first
                for (var i = 1; i <= comp.numLayers; i++) {
                    comp.layer(i).selected = false;
                }
                // Select the target layer
                comp.layer(layerIndex).selected = true;
                lastLayerName = ""; // Force refresh
                populateEffects();
                statusText.text = "Layer: " + comp.layer(layerIndex).name;
            }
        } catch (e) {
            statusText.text = "Layer select error: " + e.message;
        }
    }
    
    /**
     * Get current layer index in comp
     */
    function getCurrentLayerIndex() {
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) return -1;
            
            var layer = comp.selectedLayers[0];
            if (!layer) return -1;
            
            return layer.index;
        } catch (e) {
            return -1;
        }
    }
    
    /**
     * Check for button presses and navigate effects/layers/properties
     */
    function checkButtons() {
        var btnData = readButtonFile();
        // Update debug snapshot of position file as well
        try { readPositionFile(); } catch (e) {}
        if (verboseDebug) {
            posExistsText.text = "pos file: " + ((lastRawPositionContent && lastRawPositionContent.length > 0) ? "present" : "(empty)");
            posRawText.text = "pos raw: " + (lastRawPositionContent || "");
            btnExistsText.text = "btn file: " + ((lastRawButtonContent && lastRawButtonContent.length > 0) ? "present" : "(empty)");
            btnRawText.text = "btn raw: " + (lastRawButtonContent || "");
        }
        if (!btnData || !btnData.button) return;
        
        // Check if this is a new button event (by timestamp)
        var ts = btnData.timestamp || 0;
        if (ts <= lastButtonTimestamp) return;
        lastButtonTimestamp = ts;
        
        // Only handle press events, not releases
        if (!btnData.pressed) return;
        
        // TOP buttons: navigate EFFECTS (changed from properties)
        if (btnData.button === "TOP RIGHT" || btnData.button === "TOP LEFT") {
            var currentIdx = effectDropdown.selection ? effectDropdown.selection.index : 0;
            var newIdx = currentIdx;
            
            if (btnData.button === "TOP RIGHT") {
                // Next effect
                newIdx = currentIdx + 1;
                if (newIdx >= currentEffects.length) {
                    newIdx = 0; // Wrap around
                }
            } else if (btnData.button === "TOP LEFT") {
                // Previous effect
                newIdx = currentIdx - 1;
                if (newIdx < 0) {
                    newIdx = currentEffects.length - 1; // Wrap around
                }
            }
            
            if (newIdx !== currentIdx && currentEffects.length > 0) {
                effectDropdown.selection = newIdx;
                populateProperties();
                updateKeypadDropdowns();
                lastDialValue = null; // Reset dial tracking for new effect
                statusText.text = "Effect: " + currentEffects[newIdx].name;
            }
        }
        
        // BOTTOM buttons: navigate layers
        if (btnData.button === "BOTTOM RIGHT" || btnData.button === "BOTTOM LEFT") {
            try {
                var comp = app.project.activeItem;
                if (!comp || !(comp instanceof CompItem)) return;
                
                var currentLayerIdx = getCurrentLayerIndex();
                if (currentLayerIdx < 0) currentLayerIdx = 1;
                
                var newLayerIdx = currentLayerIdx;
                
                if (btnData.button === "BOTTOM RIGHT") {
                    // Next layer (down in layer stack)
                    newLayerIdx = currentLayerIdx + 1;
                    if (newLayerIdx > comp.numLayers) {
                        newLayerIdx = 1; // Wrap around
                    }
                } else if (btnData.button === "BOTTOM LEFT") {
                    // Previous layer (up in layer stack)
                    newLayerIdx = currentLayerIdx - 1;
                    if (newLayerIdx < 1) {
                        newLayerIdx = comp.numLayers; // Wrap around
                    }
                }
                
                if (newLayerIdx !== currentLayerIdx) {
                    selectLayerByIndex(newLayerIdx);
                }
            } catch (e) {
                statusText.text = "Layer switch error: " + e.message;
            }
        }
        
        // KEYPAD buttons 1-6: select mapped property
        if (btnData.button === "1" || btnData.button === "2" || btnData.button === "3" ||
            btnData.button === "4" || btnData.button === "5" || btnData.button === "6") {
            
            var keypadButtonIndex = parseInt(btnData.button) - 1; // Convert "1"-"6" to 0-5
            
            if (keypadButtonIndex >= 0 && keypadButtonIndex < keypadDropdowns.length) {
                var dropdown = keypadDropdowns[keypadButtonIndex];
                var propIdx = dropdown.selection ? dropdown.selection.index : 0;
                
                // propIdx 0 = "(none)", so valid properties start at index 1
                if (propIdx > 0 && propIdx <= currentProperties.length) {
                    propDropdown.selection = propIdx - 1;
                    lastDialValue = null;
                    statusText.text = "Property: " + currentProperties[propIdx - 1].name;
                }
            }
        }
        
        // KEYPAD button 7: Jump to previous keyframe
        if (btnData.button === "7") {
            try {
                var propIdx = propDropdown.selection ? propDropdown.selection.index : -1;
                if (propIdx >= 0 && propIdx < currentProperties.length) {
                    var prop = currentProperties[propIdx].prop;
                    var comp = app.project.activeItem;
                    
                    if (prop.numKeys > 0) {
                        // Find the keyframe before current time
                        var nearestKey = prop.nearestKeyIndex(comp.time);
                        var keyTime = prop.keyTime(nearestKey);
                        
                        if (keyTime >= comp.time && nearestKey > 1) {
                            // Current time is at or after this key, go to previous
                            comp.time = prop.keyTime(nearestKey - 1);
                        } else if (keyTime < comp.time) {
                            // Current time is after this key, go to it
                            comp.time = keyTime;
                        } else if (nearestKey > 1) {
                            comp.time = prop.keyTime(nearestKey - 1);
                        }
                        statusText.text = "Jumped to previous keyframe";
                    } else {
                        statusText.text = "No keyframes on this property";
                    }
                }
            } catch (e) {
                statusText.text = "Keyframe nav error: " + e.message;
            }
        }
        
        // KEYPAD button 8: Toggle keyframe at current time (add or remove)
        if (btnData.button === "8") {
            try {
                var propIdx = propDropdown.selection ? propDropdown.selection.index : -1;
                if (propIdx >= 0 && propIdx < currentProperties.length) {
                    var prop = currentProperties[propIdx].prop;
                    var comp = app.project.activeItem;
                    var currentTime = comp.time;
                    
                    // Check if there's a keyframe at current time
                    var keyAtTime = -1;
                    if (prop.numKeys > 0) {
                        var nearestKey = prop.nearestKeyIndex(currentTime);
                        var keyTime = prop.keyTime(nearestKey);
                        // Check if keyframe is at current time (within small tolerance)
                        if (Math.abs(keyTime - currentTime) < 0.001) {
                            keyAtTime = nearestKey;
                        }
                    }
                    
                    if (keyAtTime > 0) {
                        // Remove existing keyframe
                        prop.removeKey(keyAtTime);
                        statusText.text = "Keyframe removed at " + currentTime.toFixed(2) + "s";
                    } else {
                        // Add keyframe at current time with current value
                        var currentValue = prop.value;
                        prop.setValueAtTime(currentTime, currentValue);
                        statusText.text = "Keyframe added at " + currentTime.toFixed(2) + "s";
                    }
                }
            } catch (e) {
                statusText.text = "Keyframe toggle error: " + e.message;
            }
        }
        
        // KEYPAD button 9: Jump to next keyframe
        if (btnData.button === "9") {
            try {
                var propIdx = propDropdown.selection ? propDropdown.selection.index : -1;
                if (propIdx >= 0 && propIdx < currentProperties.length) {
                    var prop = currentProperties[propIdx].prop;
                    var comp = app.project.activeItem;
                    
                    if (prop.numKeys > 0) {
                        // Find the keyframe after current time
                        var nearestKey = prop.nearestKeyIndex(comp.time);
                        var keyTime = prop.keyTime(nearestKey);
                        
                        if (keyTime <= comp.time && nearestKey < prop.numKeys) {
                            // Current time is at or before this key, go to next
                            comp.time = prop.keyTime(nearestKey + 1);
                        } else if (keyTime > comp.time) {
                            // Current time is before this key, go to it
                            comp.time = keyTime;
                        } else if (nearestKey < prop.numKeys) {
                            comp.time = prop.keyTime(nearestKey + 1);
                        }
                        statusText.text = "Jumped to next keyframe";
                    } else {
                        statusText.text = "No keyframes on this property";
                    }
                }
            } catch (e) {
                statusText.text = "Keyframe nav error: " + e.message;
            }
        }
    }
    
    /**
     * Update the selected property based on dial position
     */
    function updateProperty() {
        if (!isActive) return;
        
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) {
                layerText.text = "Selected: (no comp)";
                valDisplay.text = "---";
                return;
            }
            
            var layer = comp.selectedLayers[0];
            if (!layer) {
                layerText.text = "Selected: (none)";
                valDisplay.text = "---";
                return;
            }
            
            // Check if layer changed
            if (layer.name !== lastLayerName) {
                lastLayerName = layer.name;
                layerText.text = "Selected: " + layer.name;
                populateEffects();
                lastDialValue = null;
            }
            
            // Get selected effect and property
            var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
            var propIdx = propDropdown.selection ? propDropdown.selection.index : -1;
            
            if (effectIdx < 0 || effectIdx >= currentEffects.length) {
                valDisplay.text = "(no effect)";
                return;
            }
            
            if (propIdx < 0 || propIdx >= currentProperties.length) {
                valDisplay.text = "(no property)";
                return;
            }
            
            // Get the property
            var propInfo = currentProperties[propIdx];
            var prop = propInfo.prop;
            
            // Read dial position
            var pos = readPositionFile();
            // Also sample button file for debug trace (does not alter flow)
            try {
                readButtonFile();
            } catch (e) {}
            var dialValue = pos.x;
            var smallDialValue = pos.y;

            // Update debug display if enabled
            if (verboseDebug) {
                posExistsText.text = "pos file: " + ((lastRawPositionContent && lastRawPositionContent.length > 0) ? "present" : "(empty)");
                posRawText.text = "pos raw: " + (lastRawPositionContent || "");
                btnExistsText.text = "btn file: " + ((lastRawButtonContent && lastRawButtonContent.length > 0) ? "present" : "(empty)");
                btnRawText.text = "btn raw: " + (lastRawButtonContent || "");
            }
            
            // Validate dial values
            if (typeof dialValue !== 'number' || !isFinite(dialValue)) {
                return; // Skip invalid reads
            }
            if (typeof smallDialValue !== 'number' || !isFinite(smallDialValue)) {
                smallDialValue = lastSmallDialValue || 0;
            }
            
            // Check if either dial changed
            var bigDialChanged = (dialValue !== lastDialValue);
            var smallDialChanged = (smallDialValue !== lastSmallDialValue);
            
            if (!bigDialChanged && !smallDialChanged) {
                return;
            }
            
            var dialDelta = (lastDialValue !== null) ? (dialValue - lastDialValue) : 0;
            var smallDialDelta = (lastSmallDialValue !== null) ? (smallDialValue - lastSmallDialValue) : 0;
            
            // Limit maximum delta to prevent glitches from corrupted reads
            // Use 200 to allow fast spinning while still catching file corruption
            var maxDelta = 200;
            if (Math.abs(dialDelta) > maxDelta) {
                // Likely a glitch or file corruption - ignore this update
                dialDelta = 0;
            }
            if (Math.abs(smallDialDelta) > maxDelta) {
                smallDialDelta = 0;
            }
            
            lastDialValue = dialValue;
            lastSmallDialValue = smallDialValue;
            
            // Handle small dial - timeline scrubbing (always active)
            if (smallDialDelta !== 0) {
                var timelineSensitivity = parseFloat(sensInputTimeline.text) || 1;
                var frameDelta = smallDialDelta * timelineSensitivity;
                var frameTime = comp.frameDuration;
                var newTime = comp.time + (frameDelta * frameTime);
                // Clamp to comp duration
                newTime = Math.max(0, Math.min(comp.duration - frameTime, newTime));
                comp.time = newTime;
            }
            
            // Big dial controls property - skip if no change
            if (dialDelta === 0) {
                return;
            }
            
            // Get current value
            var currentValue;
            try {
                currentValue = prop.value;
            } catch (e) {
                statusText.text = "Cannot read value: " + e.message;
                return;
            }
            
            // Skip first read (just sync and display)
            if (dialDelta === 0) {
                if (typeof currentValue === "number") {
                    valDisplay.text = currentValue.toFixed(2);
                } else if (currentValue instanceof Array) {
                    valDisplay.text = "[" + currentValue[0].toFixed(1) + ", ...]";
                } else {
                    valDisplay.text = String(currentValue);
                }
                statusText.text = "Active - Rotate dial to adjust";
                return;
            }
            
            // Calculate delta from big dial only
            var bigSensitivity = parseFloat(sensInput.text) || 0.1;
            var delta = dialDelta * bigSensitivity;
            
            try {
                // Check if property has keyframes
                var hasKeyframes = false;
                try {
                    hasKeyframes = prop.numKeys > 0;
                } catch (e) {}
                
                // Try to handle ANY property type
                if (typeof currentValue === "number") {
                    // Simple number
                    var newValue = currentValue + delta;
                    
                    if (hasKeyframes) {
                        // Add or update keyframe at current time
                        prop.setValueAtTime(comp.time, newValue);
                        valDisplay.text = newValue.toFixed(2) + " [K]";
                        statusText.text = propInfo.name + ": " + newValue.toFixed(2) + " (keyframe)";
                    } else {
                        prop.setValue(newValue);
                        valDisplay.text = newValue.toFixed(2);
                        statusText.text = propInfo.name + ": " + newValue.toFixed(2);
                    }
                    
                } else if (currentValue instanceof Array && currentValue.length > 0) {
                    // Array - adjust first component
                    var newArr = currentValue.slice();
                    if (typeof newArr[0] === "number") {
                        // For colors (0-1 range), use smaller delta
                        if (propInfo.valueType === PropertyValueType.COLOR) {
                            newArr[0] = Math.max(0, Math.min(1, newArr[0] + delta * 0.01));
                        } else {
                            newArr[0] = newArr[0] + delta;
                        }
                        
                        if (hasKeyframes) {
                            // Add or update keyframe at current time
                            prop.setValueAtTime(comp.time, newArr);
                            valDisplay.text = "[" + newArr[0].toFixed(2) + ", ...] [K]";
                            statusText.text = propInfo.name + "[0]: " + newArr[0].toFixed(2) + " (keyframe)";
                        } else {
                            prop.setValue(newArr);
                            valDisplay.text = "[" + newArr[0].toFixed(2) + ", ...]";
                            statusText.text = propInfo.name + "[0]: " + newArr[0].toFixed(2);
                        }
                    } else {
                        statusText.text = "Array[0] not numeric";
                    }
                    
                } else {
                    statusText.text = "Cannot adjust: " + (typeof currentValue);
                }
            } catch (setError) {
                statusText.text = "Cannot set: " + setError.message;
            }
            
        } catch (e) {
            statusText.text = "Error: " + e.message;
        }
    }
    
    /**
     * Start polling
     */
    function startPolling() {
        // Launch the batch file directly - hardcoded path that works
        var batPath = "C:\\Program Files\\Adobe\\Adobe After Effects 2025\\Support Files\\Scripts\\ScriptUI Panels\\logi-mx-creative-dialpad-integrations\\start_webserver_debug.bat";
        var batFile = new File(batPath);
        if (batFile.exists) {
            batFile.execute();
        } else {
            alert("Batch file not found at:\n" + batPath);
        }
        
        isActive = true;
        lastDialValue = null;
        lastLayerName = "";
        startBtn.enabled = false;
        stopBtn.enabled = true;
        
        // Refresh effects list
        populateEffects();
        
        statusText.text = "Active - Select effect & property, then rotate dial";
        
        // Start polling using an isolated global function and store task id globally
        try {
            if ($.global.logi_receiver_task_id) {
                statusText.text = "Already polling (logi).";
            } else {
                var id = app.scheduleTask("$.global.logiReceiverUpdate()", 33, true);
                $.global.logi_receiver_task_id = id;
                if (!id) alert("Failed to start polling scheduler (scheduleTask returned: " + id + ")");
                statusText.text = "Active - polling started (id:" + id + ")";
            }
        } catch (e) {
            alert("Failed to start polling: " + e.message);
        }
    }
    
    // Make update function globally accessible
        $.global.logiReceiverUpdate = function() {
            try {
                // Update a simple heartbeat so we can confirm the scheduler runs
                try { heartbeatText.text = "HB: " + (new Date()).toTimeString().split(' ')[0]; } catch (e) {}

                if (isActive) {
                    checkButtons();  // Check for button navigation
                    updateProperty();
                }
            } catch (e) {
                try { statusText.text = "Scheduler error: " + e.message; } catch (ee) {}
            }
        };
    
    /**
     * Stop polling
     */
    function stopPolling() {
        isActive = false;
        startBtn.enabled = true;
        stopBtn.enabled = false;
        statusText.text = "Stopping services...";
        valDisplay.text = "---";
        
        try {
            if ($.global.logi_receiver_task_id) {
                app.cancelTask($.global.logi_receiver_task_id);
                $.global.logi_receiver_task_id = null;
            }
        } catch (e) {}
        // Do not stop webserver here - let a central controller manage it
        statusText.text = "Stopped.";
    }
    
    /**
     * Reset dial position
     */
    function resetDial() {
        try {
            var file = new File(POSITION_FILE);
            file.open("w");
            file.write('{"x": 0, "y": 0}');
            file.close();
            lastDialValue = null;
            lastSmallDialValue = null;
            statusText.text = "Dial reset to zero.";
        } catch (e) {
            statusText.text = "Error resetting: " + e.message;
        }
    }
    
    /**
     * Debug: List all properties of selected effect (writes to file)
     */
    function debugListProperties() {
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) {
                alert("No active composition");
                return;
            }
            
            var layer = comp.selectedLayers[0];
            if (!layer) {
                alert("No layer selected");
                return;
            }
            
            var effectIdx = effectDropdown.selection ? effectDropdown.selection.index : -1;
            if (effectIdx < 0 || effectIdx >= currentEffects.length) {
                alert("No effect selected");
                return;
            }
            
            var effect = currentEffects[effectIdx].effect;
            var output = "Effect: " + effect.name + "\n";
            output += "Match Name: " + effect.matchName + "\n";
            output += "Num Properties: " + effect.numProperties + "\n\n";
            
            function listProps(parent, indent) {
                indent = indent || "";
                var result = "";
                for (var i = 1; i <= parent.numProperties; i++) {
                    try {
                        var prop = parent.property(i);
                        var info = indent + i + ". " + prop.name;
                        info += " [" + prop.matchName + "]";
                        info += " type:" + prop.propertyType;
                        
                        if (prop.propertyType === PropertyType.PROPERTY) {
                            info += " valType:" + prop.propertyValueType;
                            info += " canSet:" + prop.canSetValue;
                            try {
                                var val = prop.value;
                                if (typeof val === "number") {
                                    info += " val:" + val.toFixed(2);
                                } else if (val instanceof Array) {
                                    info += " val:[" + val.length + " items]";
                                }
                            } catch (e) {
                                info += " val:(error)";
                            }
                        }
                        result += info + "\n";
                        
                        // Recurse into groups
                        if (prop.propertyType === PropertyType.INDEXED_GROUP || 
                            prop.propertyType === PropertyType.NAMED_GROUP) {
                            result += listProps(prop, indent + "  ");
                        }
                    } catch (e) {
                        result += indent + i + ". (error: " + e.message + ")\n";
                    }
                }
                return result;
            }
            
            output += listProps(effect);
            
            // Write to file
            var debugFile = new File("C:/temp/colorista_debug.txt");
            debugFile.open("w");
            debugFile.write(output);
            debugFile.close();
            
            alert("1 Debug info written to:\nC:/temp/colorista_debug.txt\n\nOpen this file to see all properties.");
            
        } catch (e) {
            alert("Debug error: " + e.message);
        }
    }
    
    // Button handlers
    startBtn.onClick = startPolling;
    stopBtn.onClick = stopPolling;
    resetBtn.onClick = resetDial;
    refreshBtn.onClick = populateEffects;
    debugBtn.onClick = debugListProperties;
    
    // Clean up on window close
    win.onClose = function() {
        stopPolling();
    };
    
    // Initial population
    populateEffects();
    
    // Scrolling logic
    function updateScroll() {
        try {
            win.layout.layout(true);
            var contentHeight = scrollContent.size ? scrollContent.size[1] : 500;
            var viewHeight = contentGroup.size ? contentGroup.size[1] : 300;
            
            if (contentHeight > viewHeight) {
                scrollbar.visible = true;
                scrollbar.maxvalue = contentHeight - viewHeight;
                scrollbar.jumpdelta = viewHeight * 0.8;
                scrollbar.stepdelta = 30;
            } else {
                scrollbar.visible = false;
                scrollbar.value = 0;
                scrollContent.location = [0, 0];
            }
        } catch (e) {}
    }
    
    scrollbar.onChanging = scrollbar.onChange = function() {
        try {
            scrollContent.location = [0, -scrollbar.value];
        } catch (e) {}
    };
    
    // Handle resizing for dockable panels
    win.onResizing = win.onResize = function() {
        this.layout.resize();
        updateScroll();
    };
    
    // Show window (only for non-dockable panels)
    if (win instanceof Window) {
        win.center();
        win.show();
    } else {
        win.layout.layout(true);
    }
    
    // Initial scroll setup (delayed to ensure layout is complete)
    app.scheduleTask("try { $.global.logiUpdateScroll(); } catch(e) {}", 100, false);
    $.global.logiUpdateScroll = updateScroll;
})(this);