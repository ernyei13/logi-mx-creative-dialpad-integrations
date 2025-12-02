Installation notes — CEP panel for After Effects (quick test)

Overview
- This small CEP panel connects to the WebSocket broadcast at `/ws` and, when a message arrives, calls After Effects ExtendScript to adjust a Slider Control named `LogiSlider` on the first selected layer of the active comp.

Files
- `index.html` — panel UI. References `CSInterface.js` and `panel.js`.
- `panel.js` — JavaScript that opens the websocket and calls `csInterface.evalScript` to change the slider.

Prerequisites
- After Effects with CEP support (CC 2015+). `CSInterface.js` must be available in the panel folder or loaded from the CEP SDK.
- The receiver web server must be running and reachable (e.g. `ws://10.10.101.133:8080/ws`).
- In AE, select a layer in the active comp and add Effect > Expression Controls > Slider Control. Rename the effect to exactly `LogiSlider`.

Quick install (Windows) — developer/testing method
1. Create an extension folder (requires admin privileges) under:
   `C:\Program Files (x86)\Common Files\Adobe\CEP\extensions\com.logi.receiver`
2. Copy the contents of `ae_panel/` into that folder (`index.html`, `panel.js`, and a copy of `CSInterface.js`).
   - `CSInterface.js` can be copied from the CEP SDK or from an existing CEP extension: typically available at `C:\Program Files (x86)\Common Files\Adobe\CEP\CSInterface.js` or within the After Effects install resources.
3. Create a `manifest.xml` for the extension (simple manifest example below). Restart After Effects.

Example minimal `manifest.xml` (adjust version/host IDs as needed):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ExtensionManifest Version="6.0" ExtensionBundleId="com.logi.receiver.bundle" ExtensionBundleVersion="1.0.0" VersionMin="6.0">
  <ExtensionList>
    <Extension Id="com.logi.receiver" Version="1.0.0" />
  </ExtensionList>
  <ExecutionEnvironment>
    <HostList>
      <Host Name="AEFT" Version="16.0" />
    </HostList>
    <LocaleList>
      <Locale Code="All" />
    </LocaleList>
    <RequiredRuntimeList>
      <RequiredRuntime Name="CSXS" Version="6.0" />
    </RequiredRuntimeList>
  </ExecutionEnvironment>
  <DispatchInfoList>
    <Extension Id="com.logi.receiver">
      <DispatchInfo>
        <Resources>
          <MainPath>index.html</MainPath>
        </Resources>
        <Lifecycle>
          <AutoVisible>true</AutoVisible>
        </Lifecycle>
      </DispatchInfo>
    </Extension>
  </DispatchInfoList>
</ExtensionManifest>
```

Notes
- For development you may need to enable the CEP developer mode (PlayerDebugMode) in the registry so After Effects will load unsigned panels. Follow Adobe docs for enabling CEP debugging.
- Alternatively, you can copy the files into an existing, already-installed CEP extension to test quickly.

How it works
- Panel connects to the server `ws://10.10.101.133:8080/ws` by default.
- On each incoming JSON message like `{ "ctrl": "BIG", "delta": 2 }` the panel computes a delta and calls `evalScript` inside AE to increment the slider value.

If you want, I can:
- Add a complete `manifest.xml` file and optionally a simple build script to package the extension.
- Convert `panel.js` to TypeScript source plus a small build step (tsconfig + npm scripts) so you can develop in TS.

Tell me which you'd like next and I will scaffold it.
