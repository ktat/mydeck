// OpenAction plugin manager UI: list installed plugins, upload .streamDeckPlugin
// archives, and uninstall existing ones. Restart of the daemon is required for
// newly-uploaded plugins to actually run; we surface that to the user.
const Plugins = {
  data() {
    return {
      plugins: [],
      uploading: false,
      uploadStatus: null,    // {ok, message} | null
      restartRequired: false,
    };
  },
  mounted() {
    this.refresh();
  },
  methods: {
    refresh() {
      axios.get(baseURL + 'api/openaction/plugins').then((r) => {
        this.plugins = (r.data && r.data.plugins) || [];
      }).catch(() => { this.plugins = []; });
    },
    onFileChosen(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      if (!file.name.endsWith('.streamDeckPlugin')) {
        if (!confirm('File does not have .streamDeckPlugin extension. Upload anyway?')) {
          event.target.value = '';
          return;
        }
      }
      const reader = new FileReader();
      reader.onload = () => {
        // result is a data: URL; extract the base64 payload after the comma.
        const b64 = String(reader.result).split(',')[1] || '';
        this.uploadPlugin(file.name, b64);
      };
      reader.readAsDataURL(file);
      event.target.value = '';
    },
    uploadPlugin(filename, file_b64) {
      this.uploading = true;
      this.uploadStatus = null;
      axios.post(baseURL + 'api/openaction/upload',
        { filename, file_b64 },
        { headers: { 'Content-Type': 'application/json' } }
      ).then((r) => {
        if (r.data.error) {
          this.uploadStatus = { ok: false, message: r.data.error };
        } else {
          let msg = `Installed ${r.data.plugin_uuid}`;
          if (r.data.synthesized_manifest) {
            msg += ` (synthesized manifest, ${(r.data.actions || []).length} action${(r.data.actions || []).length === 1 ? '' : 's'} detected)`;
          }
          this.uploadStatus = { ok: true, message: msg };
          if (r.data.restart_required) this.restartRequired = true;
          this.refresh();
        }
      }).catch((err) => {
        this.uploadStatus = { ok: false, message: String(err) };
      }).finally(() => {
        this.uploading = false;
      });
    },
    uninstall(plugin) {
      if (!confirm(`Uninstall ${plugin.name} (${plugin.uuid})? This deletes its files from disk.`)) return;
      axios.post(baseURL + 'api/openaction/uninstall',
        { plugin_uuid: plugin.uuid },
        { headers: { 'Content-Type': 'application/json' } }
      ).then((r) => {
        if (r.data.error) {
          this.uploadStatus = { ok: false, message: r.data.error };
        } else {
          this.uploadStatus = { ok: true, message: `Uninstalled ${plugin.uuid}` };
          if (r.data.restart_required) this.restartRequired = true;
          this.refresh();
        }
      });
    },
  },
  template: `
    <div class="plugins-page" style="padding: 20px;">
      <h2>OpenAction Plugins</h2>

      <div v-if="restartRequired" style="background: #553; padding: 8px; border-radius: 4px; margin-bottom: 12px;">
        ⚠ Restart mydeck for changes to take effect (newly-uploaded plugins
        are spawned only on bridge startup).
      </div>

      <div style="margin-bottom: 20px;">
        <h3>Install a Plugin</h3>
        <input type="file" accept=".streamDeckPlugin,.zip" @change="onFileChosen" :disabled="uploading" />
        <div v-if="uploading" style="margin-top: 8px;">Uploading...</div>
        <div v-if="uploadStatus" :style="uploadStatus.ok ? 'color: #6f6;' : 'color: #f66;'" style="margin-top: 8px;">
          {{ uploadStatus.message }}
        </div>
      </div>

      <h3>Installed Plugins ({{ plugins.length }})</h3>
      <div v-if="plugins.length === 0" style="opacity: 0.7;">No plugins installed.</div>
      <div v-for="p in plugins" :key="p.uuid" style="border: 1px solid #666; padding: 10px; margin-bottom: 8px; border-radius: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <strong>{{ p.name }}</strong>
            <span style="opacity: 0.6; font-size: 12px;"> · {{ p.uuid }}</span>
          </div>
          <button @click="uninstall(p)" style="background: #844; color: white; border: 0; padding: 4px 10px; border-radius: 3px; cursor: pointer;">
            Uninstall
          </button>
        </div>
        <div style="margin-top: 6px; font-size: 12px;">
          <div v-for="a in p.actions" :key="a.uuid" style="opacity: 0.85;">
            • {{ a.name }} <span style="opacity: 0.6;">({{ a.uuid }})</span>
            <span v-if="a.property_inspector" style="color: #6f6;"> · PI</span>
          </div>
        </div>
      </div>
    </div>
  `,
};
