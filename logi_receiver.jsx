/**
 * Logi Receiver - ExtendScript for After Effects
 * Controls any effect property on the currently selected layer via Logi dial
 * 
 * Usage: File > Scripts > Run Script File... and select this file
 * 
 * The Python server writes accumulated position to C:/temp/logi_position.json
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

(function() {
    var POSITION_FILE = "C:/temp/logi_position.json";
    
    // State
    var isActive = false;
    var autoUpdateInterval = null;
    var lastDialValue = null;
    var lastLayerName = "";
    var currentEffects = [];
    var currentProperties = [];
    
    // Create UI
    var win = new Window("palette", "Logi Dial - Effect Control", undefined, {resizeable: false});
    win.orientation = "column";
    win.alignChildren = ["fill", "top"];
    
    // Status
    var statusPanel = win.add("panel", undefined, "Status");
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
    
    // Effect/Property Selection
    var targetPanel = win.add("panel", undefined, "Target Effect & Property");
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
    var sensPanel = win.add("panel", undefined, "Settings");
    sensPanel.alignChildren = ["fill", "top"];
    var sensGroup = sensPanel.add("group");
    sensGroup.add("statictext", undefined, "Sensitivity:");
    var sensInput = sensGroup.add("edittext", undefined, "0.1");
    sensInput.characters = 8;
    sensGroup.add("statictext", undefined, "(per dial tick)");
    
    // Buttons
    var buttonPanel = win.add("panel", undefined, "Controls");
    buttonPanel.alignChildren = ["fill", "top"];
    
    var btnGroup1 = buttonPanel.add("group");
    var startBtn = btnGroup1.add("button", undefined, "Start");
    var stopBtn = btnGroup1.add("button", undefined, "Stop");
    stopBtn.enabled = false;
    
    var btnGroup2 = buttonPanel.add("group");
    var resetBtn = btnGroup2.add("button", undefined, "Reset Dial");
    
    // Info
    var infoPanel = win.add("panel", undefined, "How It Works");
    infoPanel.alignChildren = ["fill", "top"];
    var infoText = infoPanel.add("statictext", undefined, 
        "1. Select a layer with effects\n" +
        "2. Choose Effect and Property from dropdowns\n" +
        "3. Click 'Start' and rotate dial!\n" +
        "4. Switch layers/effects anytime",
        {multiline: true}
    );
    infoText.preferredSize = [420, 70];
    
    // Cache for last valid position (prevents glitches from corrupted reads)
    var lastValidPosition = {x: 0, y: 0};
    
    /**
     * Read position from file with validation
     * Returns cached value if read fails or data is invalid
     */
    function readPositionFile() {
        try {
            var file = new File(POSITION_FILE);
            if (file.exists) {
                file.open("r");
                var content = file.read();
                file.close();
                
                if (content && content.length > 0) {
                    // Validate JSON structure before parsing
                    // Must start with { and end with }
                    content = content.replace(/^\s+|\s+$/g, ''); // trim
                    if (content.charAt(0) !== '{' || content.charAt(content.length - 1) !== '}') {
                        return lastValidPosition; // Corrupted, return cached
                    }
                    
                    var parsed = JSON.parse(content);
                    
                    // Validate parsed values are numbers
                    if (typeof parsed.x === 'number' && typeof parsed.y === 'number' &&
                        isFinite(parsed.x) && isFinite(parsed.y)) {
                        lastValidPosition = parsed;
                        return parsed;
                    }
                }
            }
        } catch (e) {
            // Parse error - return cached value
        }
        return lastValidPosition;
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
            var label = p.name;
            // Show current value in dropdown for easier identification
            if (typeof p.currentValue === "number") {
                label += " (" + p.currentValue.toFixed(2) + ")";
            } else if (p.currentValue instanceof Array) {
                label += " [arr]";
            }
            propDropdown.add("item", label);
        }
        propDropdown.selection = 0;
    }
    
    // Effect dropdown change handler
    effectDropdown.onChange = function() {
        populateProperties();
        lastDialValue = null;
    };
    
    // Property dropdown change handler  
    propDropdown.onChange = function() {
        lastDialValue = null;
    };
    
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
            var dialValue = pos.x;
            
            // Validate dial value
            if (typeof dialValue !== 'number' || !isFinite(dialValue)) {
                return; // Skip invalid reads
            }
            
            // Only update if dial value changed
            if (dialValue === lastDialValue) {
                return;
            }
            
            var dialDelta = (lastDialValue !== null) ? (dialValue - lastDialValue) : 0;
            
            // Limit maximum delta to prevent glitches (max 50 ticks per update)
            var maxDelta = 50;
            if (Math.abs(dialDelta) > maxDelta) {
                // Likely a glitch or file corruption - ignore this update
                lastDialValue = dialValue;
                return;
            }
            
            lastDialValue = dialValue;
            
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
            
            var sensitivity = parseFloat(sensInput.text) || 0.1;
            var delta = dialDelta * sensitivity;
            
            try {
                // Try to handle ANY property type
                if (typeof currentValue === "number") {
                    // Simple number
                    var newValue = currentValue + delta;
                    prop.setValue(newValue);
                    valDisplay.text = newValue.toFixed(2);
                    statusText.text = propInfo.name + ": " + newValue.toFixed(2);
                    
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
                        prop.setValue(newArr);
                        valDisplay.text = "[" + newArr[0].toFixed(2) + ", ...]";
                        statusText.text = propInfo.name + "[0]: " + newArr[0].toFixed(2);
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
        isActive = true;
        lastDialValue = null;
        lastLayerName = "";
        startBtn.enabled = false;
        stopBtn.enabled = true;
        
        // Refresh effects list
        populateEffects();
        
        statusText.text = "Active - Select effect & property, then rotate dial";
        
        // Start polling
        autoUpdateInterval = app.scheduleTask("$.global.logiEffectUpdate()", 50, true);
    }
    
    // Make update function globally accessible
    $.global.logiEffectUpdate = function() {
        if (isActive) {
            updateProperty();
        }
    };
    
    /**
     * Stop polling
     */
    function stopPolling() {
        isActive = false;
        startBtn.enabled = true;
        stopBtn.enabled = false;
        statusText.text = "Stopped. Click 'Start' to enable.";
        valDisplay.text = "---";
        
        if (autoUpdateInterval) {
            app.cancelTask(autoUpdateInterval);
            autoUpdateInterval = null;
        }
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
            
            alert("Debug info written to:\nC:/temp/colorista_debug.txt\n\nOpen this file to see all properties.");
            
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
    
    // Show window
    win.show();
})();