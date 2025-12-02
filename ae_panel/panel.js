// Compiled JS for CEP panel (can be generated from TS). Minimal dependency on CSInterface.
(function () {
    'use strict';

    var csInterface = null;
    try {
        csInterface = new CSInterface();
    } catch (e) {
        console.warn('CSInterface not available. Are you running inside CEP?');
    }

    var led = document.getElementById('led');
    var status = document.getElementById('status');
    var hostInput = document.getElementById('host');
    var btn = document.getElementById('btnConnect');

    var ws = null;

    function setLed(ok) {
        if (ok) {
            led.className = 'led green';
            status.textContent = 'Connected';
        } else {
            led.className = 'led red';
            status.textContent = 'Disconnected';
        }
    }

    function connect() {
        var url = hostInput.value;
        if (ws) {
            try { ws.close(); } catch (e) {}
            ws = null;
        }
        try {
            ws = new WebSocket(url);
        } catch (e) {
            alert('WebSocket error: ' + e);
            return;
        }

        ws.onopen = function () {
            setLed(true);
            console.log('ws open');
        };
        ws.onclose = function () {
            setLed(false);
            console.log('ws close');
        };
        ws.onerror = function (ev) {
            console.warn('ws error', ev);
            setLed(false);
        };
        ws.onmessage = function (ev) {
            try {
                var data = JSON.parse(ev.data);
                // data: { ctrl: "BIG"|"SMALL", delta: number }
                handleMessage(data);
            } catch (e) {
                console.warn('invalid msg', ev.data);
            }
        };
    }

    function handleMessage(msg) {
        // Map incoming control to slider changes. You can adjust behavior here.
        var sliderName = 'LogiSlider';
        var delta = Number(msg.delta) || 0;
        // For BIG/SMALL differentiate scaling
        var amount = delta;
        if (msg.ctrl === 'BIG') amount = delta * 1.0; // tune multiplier
        if (msg.ctrl === 'SMALL') amount = delta * 0.5;

        // Call ExtendScript to apply the delta to selected layer's slider effect
        if (csInterface) {
            var esc = '' +
                "(function(effectName, delta){\n" +
                "    try{\n" +
                "        var comp = app.project.activeItem;\n" +
                "        if(!comp || !(comp instanceof CompItem)) return 'NO_COMP';\n" +
                "        if(comp.selectedLayers.length===0) return 'NO_LAYER';\n" +
                "        var layer = comp.selectedLayers[0];\n" +
                "        var fx = layer.property('ADBE Effect Parade').property(effectName);\n" +
                "        if(!fx) return 'NO_EFFECT';\n" +
                "        var slider = fx.property(1); // first param of Slider Control\n" +
                "        var cur = slider.value;\n" +
                "        slider.setValue(cur + delta);\n" +
                "        return 'OK:'+slider.value;\n" +
                "    }catch(e){ return 'ERR:'+e.toString(); }\n" +
                "})";
            // escape params
            var call = esc + "('" + sliderName + "', " + amount + ")";
            csInterface.evalScript(call, function (res) {
                console.log('evalScript result:', res);
            });
        }
    }

    btn.addEventListener('click', function () {
        connect();
    });

    // try auto-connect once
    window.addEventListener('load', function () {
        setTimeout(function () { connect(); }, 200);
    });

})();
