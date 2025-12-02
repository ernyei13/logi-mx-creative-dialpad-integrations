/**
 * Logi Receiver - ExtendScript for After Effects
 * Updates layer Position directly by reading a command file
 * 
 * Usage: File > Scripts > Run Script File... and select this file
 * 
 * The Python server writes accumulated position to C:/temp/logi_position.json
 * This script reads that file and updates the layer position!
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
    var targetLayer = null;
    var basePosition = [0, 0];
    var isLinked = false;
    var lastOffsetX = null;
    var lastOffsetY = null;
    var autoUpdateInterval = null;
    
    // Create UI
    var win = new Window("palette", "Logi Dial Control", undefined, {resizeable: false});
    win.orientation = "column";
    win.alignChildren = ["fill", "top"];
    
    // Status
    var statusPanel = win.add("panel", undefined, "Status");
    statusPanel.alignChildren = ["fill", "top"];
    var statusText = statusPanel.add("statictext", undefined, "Select a layer and click 'Link Layer'");
    statusText.characters = 50;
    
    // Linked layer display
    var linkedText = statusPanel.add("statictext", undefined, "No layer linked");
    linkedText.characters = 40;
    
    // Live position display
    var posDisplayGroup = statusPanel.add("group");
    posDisplayGroup.orientation = "row";
    posDisplayGroup.add("statictext", undefined, "Dial offset - X:");
    var posXDisplay = posDisplayGroup.add("statictext", undefined, "0");
    posXDisplay.characters = 8;
    posDisplayGroup.add("statictext", undefined, "Y:");
    var posYDisplay = posDisplayGroup.add("statictext", undefined, "0");
    posYDisplay.characters = 8;
    
    // Axis selection
    var axisPanel = win.add("panel", undefined, "Axis Control");
    axisPanel.alignChildren = ["fill", "top"];
    var axisGroup = axisPanel.add("group");
    axisGroup.add("statictext", undefined, "Control axis:");
    var axisDropdown = axisGroup.add("dropdownlist", undefined, ["X (Horizontal)", "Y (Vertical)", "Both"]);
    axisDropdown.selection = 0;
    
    // Sensitivity
    var sensGroup = axisPanel.add("group");
    sensGroup.add("statictext", undefined, "Sensitivity:");
    var sensInput = sensGroup.add("edittext", undefined, "1");
    sensInput.characters = 6;
    sensGroup.add("statictext", undefined, "(multiplier)");
    
    // Buttons
    var buttonPanel = win.add("panel", undefined, "Controls");
    buttonPanel.alignChildren = ["fill", "top"];
    
    var btnGroup1 = buttonPanel.add("group");
    var linkBtn = btnGroup1.add("button", undefined, "Link Layer");
    var unlinkBtn = btnGroup1.add("button", undefined, "Unlink");
    unlinkBtn.enabled = false;
    
    var btnGroup2 = buttonPanel.add("group");
    var resetBtn = btnGroup2.add("button", undefined, "Reset Dial");
    
    // Info
    var infoPanel = win.add("panel", undefined, "How It Works");
    infoPanel.alignChildren = ["fill", "top"];
    var infoText = infoPanel.add("statictext", undefined, 
        "1. Select a layer and click 'Link Layer'\n" +
        "2. Rotate the dial - position updates LIVE!\n" +
        "3. Click 'Unlink' when done\n\n" +
        "File: " + POSITION_FILE,
        {multiline: true}
    );
    infoText.preferredSize = [420, 80];
    
    /**
     * Read position from file
     */
    function readPositionFile() {
        try {
            var file = new File(POSITION_FILE);
            if (file.exists) {
                file.open("r");
                var content = file.read();
                file.close();
                if (content) {
                    return JSON.parse(content);
                }
            }
        } catch (e) {}
        return {x: 0, y: 0};
    }
    
    /**
     * Update the layer position based on file (only if changed)
     */
    function updateLayerPosition() {
        if (!isLinked || !targetLayer) {
            return;
        }
        
        try {
            // Check if layer still exists
            try {
                var test = targetLayer.name;
            } catch (e) {
                unlinkLayer();
                statusText.text = "Layer was deleted.";
                return;
            }
            
            var pos = readPositionFile();
            var sensitivity = parseFloat(sensInput.text) || 1;
            var axisChoice = axisDropdown.selection.index;
            
            var offsetX = (pos.x || 0) * sensitivity;
            var offsetY = (pos.y || 0) * sensitivity;
            
            // Only update if values changed
            if (offsetX === lastOffsetX && offsetY === lastOffsetY) {
                return;
            }
            
            lastOffsetX = offsetX;
            lastOffsetY = offsetY;
            
            posXDisplay.text = Math.round(offsetX);
            posYDisplay.text = Math.round(offsetY);
            
            var newX = basePosition[0];
            var newY = basePosition[1];
            
            if (axisChoice === 0 || axisChoice === 2) {
                newX = basePosition[0] + offsetX;
            }
            if (axisChoice === 1 || axisChoice === 2) {
                newY = basePosition[1] + offsetY;
            }
            
            var positionProp = targetLayer.property("Transform").property("Position");
            
            if (basePosition.length === 3) {
                positionProp.setValue([newX, newY, basePosition[2]]);
            } else {
                positionProp.setValue([newX, newY]);
            }
            
            statusText.text = "Live updating...";
            
        } catch (e) {
            statusText.text = "Error: " + e.message;
        }
    }
    
    /**
     * Start auto-update polling
     */
    function startAutoUpdate() {
        // Use a ScriptUI task for polling
        var pollFunction = function() {
            updateLayerPosition();
            if (isLinked) {
                win.update();
            }
        };
        
        // Poll every 50ms using onIdle
        autoUpdateInterval = app.scheduleTask("$.global.logiUpdate()", 50, true);
    }
    
    // Make update function globally accessible for scheduleTask
    $.global.logiUpdate = function() {
        if (isLinked && targetLayer) {
            updateLayerPosition();
        }
    };
    
    /**
     * Stop auto-update polling
     */
    function stopAutoUpdate() {
        if (autoUpdateInterval) {
            app.cancelTask(autoUpdateInterval);
            autoUpdateInterval = null;
        }
    }
    
    /**
     * Link to selected layer
     */
    function linkLayer() {
        try {
            var comp = app.project.activeItem;
            if (!comp || !(comp instanceof CompItem)) {
                statusText.text = "Error: No active composition";
                return;
            }
            
            var layer = comp.selectedLayers[0];
            if (!layer) {
                statusText.text = "Error: No layer selected";
                return;
            }
            
            targetLayer = layer;
            var positionProp = layer.property("Transform").property("Position");
            basePosition = positionProp.value.slice(); // Copy array
            lastOffsetX = null;
            lastOffsetY = null;
            
            isLinked = true;
            linkBtn.enabled = false;
            unlinkBtn.enabled = true;
            linkedText.text = "Linked to: " + layer.name;
            statusText.text = "LIVE MODE - Rotate dial to move layer!";
            
            // Read current offset
            var pos = readPositionFile();
            posXDisplay.text = Math.round(pos.x || 0);
            posYDisplay.text = Math.round(pos.y || 0);
            
            // Start auto-update
            startAutoUpdate();
            
        } catch (e) {
            statusText.text = "Error: " + e.message;
        }
    }
    
    /**
     * Unlink layer
     */
    function unlinkLayer() {
        stopAutoUpdate();
        isLinked = false;
        targetLayer = null;
        linkBtn.enabled = true;
        unlinkBtn.enabled = false;
        linkedText.text = "No layer linked";
        statusText.text = "Layer unlinked. Position retained.";
    }
    
    /**
     * Reset position file to zero
     */
    function resetPosition() {
        try {
            var file = new File(POSITION_FILE);
            file.open("w");
            file.write('{"x": 0, "y": 0}');
            file.close();
            posXDisplay.text = "0";
            posYDisplay.text = "0";
            lastOffsetX = null;
            lastOffsetY = null;
            
            // Also reset base position to current if linked
            if (isLinked && targetLayer) {
                var positionProp = targetLayer.property("Transform").property("Position");
                basePosition = positionProp.value.slice();
            }
            
            statusText.text = "Dial position reset to zero.";
        } catch (e) {
            statusText.text = "Error resetting: " + e.message;
        }
    }
    
    // Button handlers
    linkBtn.onClick = linkLayer;
    unlinkBtn.onClick = unlinkLayer;
    resetBtn.onClick = resetPosition;
    
    // Clean up on window close
    win.onClose = function() {
        stopAutoUpdate();
    };
    
    // Show initial offset from file
    var initPos = readPositionFile();
    posXDisplay.text = Math.round(initPos.x || 0);
    posYDisplay.text = Math.round(initPos.y || 0);
    
    // Show window
    win.show();
})();