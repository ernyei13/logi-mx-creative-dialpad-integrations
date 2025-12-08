/**
 * MIDI Receiver - ExtendScript for After Effects
 * Controls layer properties via MIDI controller (Novation Launch Control XL)
 * 
 * Default mappings:
 * - Faders 1-8: Layer 1-8 Opacity
 * - Knobs Row A: Layer 1-8 X Position
 * - Knobs Row B: Layer 1-8 Y Position  
 * - Knobs Row C: Layer 1-8 Blend Mode (cycles through modes)
 * - Focus buttons 1-8: Layer 1-8 Visibility toggle
 * - Ctrl buttons 1-8: Layer 1-8 Solo toggle
 * 
 * Reads from: C:/temp/controller_state.json (written by web_server.py)
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
    var STATE_FILE = "C:/temp/controller_state.json";
    
    // State
    var isActive = false;
    var autoUpdateInterval = null;
    var lastStateTimestamp = 0;
    
    // Track last values to detect changes
    var lastFaderValues = [0, 0, 0, 0, 0, 0, 0, 0];
    var lastKnobAValues = [0, 0, 0, 0, 0, 0, 0, 0];
    var lastKnobBValues = [0, 0, 0, 0, 0, 0, 0, 0];
    var lastKnobCValues = [0, 0, 0, 0, 0, 0, 0, 0];
    var lastFocusStates = [false, false, false, false, false, false, false, false];
    var lastCtrlStates = [false, false, false, false, false, false, false, false];
    var lastAuxStates = [false, false, false, false, false, false, false, false];
    
    // Mapping options
    var PROPERTY_OPTIONS = [
        "(none)",
        "Opacity",
        "Position X",
        "Position Y",
        "Scale",
        "Rotation",
        "Anchor X",
        "Anchor Y"
    ];
    
    var BUTTON_OPTIONS = [
        "(none)",
        "Visibility (Eye)",
        "Solo",
        "Lock",
        "Shy",
        "Collapse/Expand",
        "Quality",
        "Effects",
        "Frame Blend",
        "Motion Blur",
        "Adjustment Layer",
        "3D Layer",
        "Guide Layer"
    ];
    
    // Blend modes list
    var BLEND_MODES = [
        BlendingMode.NORMAL,
        BlendingMode.MULTIPLY,
        BlendingMode.SCREEN,
        BlendingMode.OVERLAY,
        BlendingMode.SOFT_LIGHT,
        BlendingMode.HARD_LIGHT,
        BlendingMode.ADD,
        BlendingMode.DIFFERENCE
    ];
    var BLEND_MODE_NAMES = ["Normal", "Multiply", "Screen", "Overlay", "Soft Light", "Hard Light", "Add", "Difference"];
    
    // Current mappings (indices into PROPERTY_OPTIONS / BUTTON_OPTIONS)
    var mappings = {
        fader: 1,      // Opacity
        knobA: 2,      // Position X
        knobB: 3,      // Position Y
        knobC: 0,      // Blend Mode (special - uses index 0 for blend mode)
        focus: 1,      // Visibility
        ctrl: 2        // Solo
    };
    
    // Build UI
    function buildUI(thisObj) {
        var win = (thisObj instanceof Panel) ? thisObj : new Window("palette", "MIDI Layer Control", undefined, {resizeable: true});
        return win;
    }
    
    var win = buildUI(thisObj);
    win.orientation = "column";
    win.alignChildren = ["fill", "top"];
    win.spacing = 4;
    win.margins = 8;
    
    // Status Panel
    var statusPanel = win.add("panel", undefined, "Status");
    statusPanel.alignChildren = ["fill", "top"];
    var statusText = statusPanel.add("statictext", undefined, "Click Start to begin MIDI control");
    statusText.characters = 45;
    
    // Mappings Panel - single row for each control type
    var mappingsPanel = win.add("panel", undefined, "Control Mappings (applies to all 8 channels)");
    mappingsPanel.alignChildren = ["fill", "top"];
    
    // Fader mapping
    var faderGroup = mappingsPanel.add("group");
    faderGroup.add("statictext", undefined, "Faders:");
    var faderDropdown = faderGroup.add("dropdownlist", undefined, PROPERTY_OPTIONS);
    faderDropdown.selection = mappings.fader;
    faderDropdown.preferredSize = [120, 25];
    
    // Knob A mapping
    var knobAGroup = mappingsPanel.add("group");
    knobAGroup.add("statictext", undefined, "Knobs A:");
    var knobADropdown = knobAGroup.add("dropdownlist", undefined, PROPERTY_OPTIONS);
    knobADropdown.selection = mappings.knobA;
    knobADropdown.preferredSize = [120, 25];
    
    // Knob B mapping
    var knobBGroup = mappingsPanel.add("group");
    knobBGroup.add("statictext", undefined, "Knobs B:");
    var knobBDropdown = knobBGroup.add("dropdownlist", undefined, PROPERTY_OPTIONS);
    knobBDropdown.selection = mappings.knobB;
    knobBDropdown.preferredSize = [120, 25];
    
    // Knob C mapping (special - Blend Mode)
    var knobCGroup = mappingsPanel.add("group");
    knobCGroup.add("statictext", undefined, "Knobs C:");
    var knobCOptions = ["Blend Mode"].concat(PROPERTY_OPTIONS.slice(1));
    var knobCDropdown = knobCGroup.add("dropdownlist", undefined, knobCOptions);
    knobCDropdown.selection = 0; // Blend Mode by default
    knobCDropdown.preferredSize = [120, 25];
    
    // Focus button mapping
    var focusGroup = mappingsPanel.add("group");
    focusGroup.add("statictext", undefined, "Focus Btns:");
    var focusDropdown = focusGroup.add("dropdownlist", undefined, BUTTON_OPTIONS);
    focusDropdown.selection = mappings.focus;
    focusDropdown.preferredSize = [120, 25];
    
    // Ctrl button mapping
    var ctrlGroup = mappingsPanel.add("group");
    ctrlGroup.add("statictext", undefined, "Ctrl Btns:");
    var ctrlDropdown = ctrlGroup.add("dropdownlist", undefined, BUTTON_OPTIONS);
    ctrlDropdown.selection = mappings.ctrl;
    ctrlDropdown.preferredSize = [120, 25];
    
    // Buttons
    var buttonPanel = win.add("panel", undefined, "Controls");
    buttonPanel.alignChildren = ["fill", "top"];
    
    var btnGroup = buttonPanel.add("group");
    var startBtn = btnGroup.add("button", undefined, "Start");
    var stopBtn = btnGroup.add("button", undefined, "Stop");
    stopBtn.enabled = false;
    
    // Dropdown change handlers
    faderDropdown.onChange = function() { mappings.fader = faderDropdown.selection.index; };
    knobADropdown.onChange = function() { mappings.knobA = knobADropdown.selection.index; };
    knobBDropdown.onChange = function() { mappings.knobB = knobBDropdown.selection.index; };
    knobCDropdown.onChange = function() { mappings.knobC = knobCDropdown.selection.index; };
    focusDropdown.onChange = function() { mappings.focus = focusDropdown.selection.index; };
    ctrlDropdown.onChange = function() { mappings.ctrl = ctrlDropdown.selection.index; };
    
    /**
     * Read controller state from file
     */
    function readStateFile() {
        try {
            var f = new File(STATE_FILE);
            if (!f.exists) return null;
            
            f.open("r");
            var content = f.read();
            f.close();
            
            if (!content || content.length < 2) return null;
            
            return JSON.parse(content);
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Get layer by index (1-based)
     */
    function getLayer(layerIndex) {
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) return null;
            if (layerIndex < 1 || layerIndex > comp.numLayers) return null;
            return comp.layer(layerIndex);
        } catch (e) {
            return null;
        }
    }
    
    /**
     * Apply property value to a layer based on mapping
     * @param layer - the layer
     * @param mappingIndex - index into PROPERTY_OPTIONS
     * @param normalizedValue - 0-100 value
     */
    function applyPropertyValue(layer, mappingIndex, normalizedValue) {
        if (!layer || mappingIndex <= 0) return;
        
        try {
            switch (mappingIndex) {
                case 1: // Opacity
                    layer.opacity.setValue(normalizedValue);
                    break;
                case 2: // Position X
                    var pos = layer.position.value;
                    // Map 0-100 to comp width range
                    var comp = app.project.activeItem;
                    var newX = (normalizedValue / 100) * comp.width;
                    layer.position.setValue([newX, pos[1]]);
                    break;
                case 3: // Position Y
                    var pos = layer.position.value;
                    var comp = app.project.activeItem;
                    var newY = (normalizedValue / 100) * comp.height;
                    layer.position.setValue([pos[0], newY]);
                    break;
                case 4: // Scale
                    var scale = normalizedValue * 2; // 0-200%
                    layer.scale.setValue([scale, scale]);
                    break;
                case 5: // Rotation
                    var rot = (normalizedValue / 100) * 360; // 0-360
                    layer.rotation.setValue(rot);
                    break;
                case 6: // Anchor X
                    var anchor = layer.anchorPoint.value;
                    var comp = app.project.activeItem;
                    var newAX = (normalizedValue / 100) * comp.width;
                    layer.anchorPoint.setValue([newAX, anchor[1]]);
                    break;
                case 7: // Anchor Y
                    var anchor = layer.anchorPoint.value;
                    var comp = app.project.activeItem;
                    var newAY = (normalizedValue / 100) * comp.height;
                    layer.anchorPoint.setValue([anchor[0], newAY]);
                    break;
            }
        } catch (e) {
            // Property may not exist or be locked
        }
    }
    
    /**
     * Apply blend mode to a layer
     * @param layer - the layer
     * @param normalizedValue - 0-100 value (maps to blend mode index)
     */
    function applyBlendMode(layer, normalizedValue) {
        if (!layer) return;
        
        try {
            // Map 0-100 to blend mode index
            var modeIndex = Math.floor((normalizedValue / 100) * (BLEND_MODES.length - 1));
            modeIndex = Math.max(0, Math.min(modeIndex, BLEND_MODES.length - 1));
            layer.blendingMode = BLEND_MODES[modeIndex];
        } catch (e) {}
    }
    
    /**
     * Apply button action to a layer
     * @param layer - the layer
     * @param mappingIndex - index into BUTTON_OPTIONS
     * @param pressed - boolean, true if button just pressed
     */
    function applyButtonAction(layer, mappingIndex, pressed) {
        if (!layer || mappingIndex <= 0 || !pressed) return;
        
        try {
            switch (mappingIndex) {
                case 1: // Visibility (Eye)
                    layer.enabled = !layer.enabled;
                    break;
                case 2: // Solo
                    layer.solo = !layer.solo;
                    break;
                case 3: // Lock
                    layer.locked = !layer.locked;
                    break;
                case 4: // Shy
                    layer.shy = !layer.shy;
                    break;
                case 5: // Collapse/Expand (for precomps)
                    if (layer.canSetCollapseTransformation) {
                        layer.collapseTransformation = !layer.collapseTransformation;
                    }
                    break;
                case 6: // Quality (Best/Draft)
                    if (layer.quality === LayerQuality.BEST) {
                        layer.quality = LayerQuality.DRAFT;
                    } else {
                        layer.quality = LayerQuality.BEST;
                    }
                    break;
                case 7: // Effects on/off
                    layer.effectsActive = !layer.effectsActive;
                    break;
                case 8: // Frame Blend
                    if (layer.frameBlendingType === FrameBlendingType.NO_FRAME_BLEND) {
                        layer.frameBlendingType = FrameBlendingType.FRAME_MIX;
                    } else {
                        layer.frameBlendingType = FrameBlendingType.NO_FRAME_BLEND;
                    }
                    break;
                case 9: // Motion Blur
                    layer.motionBlur = !layer.motionBlur;
                    break;
                case 10: // Adjustment Layer
                    layer.adjustmentLayer = !layer.adjustmentLayer;
                    break;
                case 11: // 3D Layer
                    layer.threeDLayer = !layer.threeDLayer;
                    break;
                case 12: // Guide Layer
                    layer.guideLayer = !layer.guideLayer;
                    break;
            }
        } catch (e) {
            // Some properties may not be available for certain layer types
        }
    }

    /**
     * Apply auxiliary action mapped from special MIDI notes (aux_1..aux_4)
     * auxIndex: 1-4
     */
    function applyAuxAction(layer, auxIndex) {
        if (!layer) return;
        try {
            switch (auxIndex) {
                case 1:
                    // Collapse/Expand (precomp collapse)
                    if (layer.canSetCollapseTransformation) layer.collapseTransformation = !layer.collapseTransformation;
                    break;
                case 2:
                    // Lock layer
                    layer.locked = !layer.locked;
                    break;
                case 3:
                    // Shy toggle
                    layer.shy = !layer.shy;
                    break;
                case 4:
                    // Motion blur toggle
                    layer.motionBlur = !layer.motionBlur;
                    break;
            }
        } catch (e) {
            // ignore unsupported properties
        }
    }
    
    /**
     * Main update loop - read state and apply to layers
     */
    function updateFromMIDI() {
        if (!isActive) return;
        
        var state = readStateFile();
        if (!state) {
            statusText.text = "Cannot read state file";
            return;
        }
        
        // Check if state has updated
        var ts = state.last_update || 0;
        if (ts <= lastStateTimestamp) return;
        lastStateTimestamp = ts;
        
        var comp = app.project.activeItem;
        if (!comp || !(comp instanceof CompItem)) {
            statusText.text = "No composition active";
            return;
        }
        
        // Show fader 1 value for debugging
        statusText.text = "F1:" + (state.fader_1 || 0).toFixed(0) + " Layers:" + comp.numLayers;
        
        // Process each channel (1-8)
        for (var i = 0; i < 8; i++) {
            var layerIndex = i + 1;
            var layer = getLayer(layerIndex);
            if (!layer) continue;
            
            // Faders
            var faderKey = "fader_" + (i + 1);
            var faderVal = state[faderKey] || 0;
            if (faderVal !== lastFaderValues[i]) {
                lastFaderValues[i] = faderVal;
                applyPropertyValue(layer, mappings.fader, faderVal);
            }
            
            // Knobs A
            var knobAKey = "knob_" + (i + 1) + "a";
            var knobAVal = state[knobAKey] || 0;
            if (knobAVal !== lastKnobAValues[i]) {
                lastKnobAValues[i] = knobAVal;
                applyPropertyValue(layer, mappings.knobA, knobAVal);
            }
            
            // Knobs B
            var knobBKey = "knob_" + (i + 1) + "b";
            var knobBVal = state[knobBKey] || 0;
            if (knobBVal !== lastKnobBValues[i]) {
                lastKnobBValues[i] = knobBVal;
                applyPropertyValue(layer, mappings.knobB, knobBVal);
            }
            
            // Knobs C (special - blend mode or property)
            var knobCKey = "knob_" + (i + 1) + "c";
            var knobCVal = state[knobCKey] || 0;
            if (knobCVal !== lastKnobCValues[i]) {
                lastKnobCValues[i] = knobCVal;
                if (mappings.knobC === 0) {
                    // Blend mode
                    applyBlendMode(layer, knobCVal);
                } else {
                    // Regular property (offset by 1 because we added "Blend Mode" at index 0)
                    applyPropertyValue(layer, mappings.knobC, knobCVal);
                }
            }
            
            // Focus buttons - trigger on any state change (host.py toggles ON/OFF)
            var focusKey = "focus_" + (i + 1);
            var focusVal = state[focusKey] || false;
            if (focusVal !== lastFocusStates[i]) {
                lastFocusStates[i] = focusVal;
                // Trigger action on any change (both ON and OFF are button presses)
                applyButtonAction(layer, mappings.focus, true);
            }
            
            // Ctrl buttons - trigger on any state change (host.py toggles ON/OFF)
            var ctrlKey = "ctrl_" + (i + 1);
            var ctrlVal = state[ctrlKey] || false;
            if (ctrlVal !== lastCtrlStates[i]) {
                lastCtrlStates[i] = ctrlVal;
                // Trigger action on any change (both ON and OFF are button presses)
                applyButtonAction(layer, mappings.ctrl, true);
            }

            // Aux buttons (mapped from raw MIDI notes 105-108 -> aux_1..aux_4)
            var auxKey = "aux_" + (i + 1);
            var auxVal = state[auxKey] || false;
            if (auxVal !== lastAuxStates[i]) {
                lastAuxStates[i] = auxVal;
                if (auxVal) {
                    // Only act on press (true)
                    applyAuxAction(layer, i + 1);
                }
            }
        }
        
        // Keep the fader debug info visible (don't overwrite)
    }
    
    /**
     * Start polling
     */
    function startPolling() {
        isActive = true;
        lastStateTimestamp = 0;
        
        // Reset last values
        for (var i = 0; i < 8; i++) {
            lastFaderValues[i] = 0;
            lastKnobAValues[i] = 0;
            lastKnobBValues[i] = 0;
            lastKnobCValues[i] = 0;
            lastFocusStates[i] = false;
            lastCtrlStates[i] = false;
            lastAuxStates[i] = false;
        }
        
        startBtn.enabled = false;
        stopBtn.enabled = true;
        statusText.text = "Active - waiting for MIDI input...";
        
        // Start polling at 33ms (~30fps) - balanced for responsiveness vs CPU
        try {
            if ($.global.midi_receiver_task_id) {
                statusText.text = "Already polling (midi).";
            } else {
                var id = app.scheduleTask("$.global.midiReceiverUpdate()", 33, true);
                $.global.midi_receiver_task_id = id;
                if (!id) alert("Failed to start MIDI scheduler (scheduleTask returned: " + id + ")");
                statusText.text = "Active - MIDI polling started (id:" + id + ")";
            }
        } catch (e) {
            alert("Error starting MIDI poller: " + e.message);
        }
    }
    
    // Make update function globally accessible
    $.global.midiReceiverUpdate = function() {
        if (isActive) {
            updateFromMIDI();
        }
    };
    
    /**
     * Stop polling
     */
    function stopPolling() {
        isActive = false;
        startBtn.enabled = true;
        stopBtn.enabled = false;
        statusText.text = "Stopped";
        
        try {
            if ($.global.midi_receiver_task_id) {
                app.cancelTask($.global.midi_receiver_task_id);
                $.global.midi_receiver_task_id = null;
            }
        } catch (e) {}
    }
    
    // Button handlers
    startBtn.onClick = startPolling;
    stopBtn.onClick = stopPolling;
    
    // Clean up on window close
    win.onClose = function() {
        stopPolling();
    };
    
    // Handle resizing for dockable panels
    win.onResizing = win.onResize = function() {
        this.layout.resize();
    };
    
    // Show window
    if (win instanceof Window) {
        win.center();
        win.show();
    } else {
        win.layout.layout(true);
    }
    
})(this);
