{
    function buildBatLauncher(thisObj) {
        // --- PREFERENCES & SETTINGS ---
        var scriptName = "BatLauncher";
        var settingsSection = "BatLauncher_Settings";
        var settingsKey = "LastBatPath";

        // --- UI CREATION ---
        var win = (thisObj instanceof Panel) ? thisObj : new Window("palette", "Batch File Launcher", undefined, {resizeable: true});
        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.spacing = 10;
        win.margins = 16;

        // Group 1: Path Selection
        var pathGroup = win.add("group");
        pathGroup.orientation = "row";
        pathGroup.alignChildren = ["fill", "center"];
        
        var pathLabel = pathGroup.add("statictext", undefined, "Path:");
        
        // The text input field
        var pathInput = pathGroup.add("edittext", undefined, "");
        pathInput.preferredSize.width = 200;
        pathInput.helpTip = "The full path to your .bat file";

        var btnBrowse = pathGroup.add("button", undefined, "Browse...");
        btnBrowse.preferredSize.width = 70;

        // Group 2: Action Buttons
        var actionGroup = win.add("group");
        actionGroup.orientation = "row";
        actionGroup.alignChildren = ["fill", "center"];

        var btnRun = actionGroup.add("button", undefined, "Run Batch File");
        btnRun.preferredSize.height = 40; // Make it big and clickable

        // --- HELPER FUNCTIONS ---

        // Function to save the path to AE preferences so it remembers next time
        function savePathPreference(path) {
            if (app.settings && app.preferences) {
                app.settings.saveSetting(settingsSection, settingsKey, path);
            }
        }

        // Function to load the path from AE preferences
        function loadPathPreference() {
            if (app.settings && app.preferences) {
                if (app.settings.haveSetting(settingsSection, settingsKey)) {
                    return app.settings.getSetting(settingsSection, settingsKey);
                }
            }
            return "";
        }

        // --- EVENT HANDLERS ---

        // 1. Initialize: Load last used path
        pathInput.text = loadPathPreference();

        // 2. Browse Button Click
        btnBrowse.onClick = function() {
            // Filter for .bat and .cmd files
            var filter = ($.os.indexOf("Windows") !== -1) ? "Batch Files:*.bat;*.cmd" : "*.*";
            
            var file = File.openDialog("Select a Batch file", filter);
            
            if (file) {
                // fsName provides the OS specific path (backslashes for Windows)
                pathInput.text = file.fsName;
                savePathPreference(file.fsName);
            }
        };

        // 3. Run Button Click
        btnRun.onClick = function() {
            var currentPath = pathInput.text;

            if (currentPath === "") {
                alert("Please select a file first.");
                return;
            }

            var batFile = new File(currentPath);

            if (batFile.exists) {
                // OPTION 1: Execute directly (Standard behavior)
                // This opens the file as if you double-clicked it.
                batFile.execute();

                // OPTION 2: System Call (Alternative)
                // Use this ONLY if Option 1 doesn't work for your specific needs.
                // Note: This requires "Allow Scripts to Write Files" in AE Preferences.
                // system.callSystem("cmd /c \"" + batFile.fsName + "\"");
            } else {
                alert("File not found at:\n" + currentPath);
            }
        };

        // --- FINAL LAYOUT ---
        win.layout.layout(true);
        win.onResizing = win.onResize = function() {
            this.layout.resize();
        };
        
        return win;
    }

    // Display the Window
    var myScriptPal = buildBatLauncher(this);
    if ((myScriptPal != null) && (myScriptPal instanceof Window)) {
        myScriptPal.center();
        myScriptPal.show();
    }
}