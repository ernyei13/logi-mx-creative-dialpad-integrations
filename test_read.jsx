// Test script to check if AE can read controller_state.json
var STATE_FILE = "C:/temp/controller_state.json";

try {
    var f = new File(STATE_FILE);
    alert("File exists: " + f.exists + "\nPath: " + f.fsName);
    
    if (f.exists) {
        f.open("r");
        var content = f.read();
        f.close();
        
        alert("Content length: " + content.length + "\nFirst 200 chars:\n" + content.substring(0, 200));
        
        // Try to parse
        var data = eval('(' + content + ')');
        alert("Parsed OK!\nfader_1: " + data.fader_1 + "\nlast_update: " + data.last_update);
    }
} catch (e) {
    alert("Error: " + e.message);
}
