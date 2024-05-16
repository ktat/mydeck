// very simple validation definition
const required = {
  'chrome': {
    'chrome': [{ name: 'url', type: 'array' }, [[{ name: 'profile', type: 'string' }], [{ name: 'url', type: 'url' }]]],
    'image': [{ type: 'path?' }],
    'label': [{ type: 'string' }],
  },
  'command': {
    'command': [{ type: 'string' }],
    'image': [{ type: 'path' }],
    'label': [{ type: 'string' }],
  },
  'deck_command': {
    'deck_command': [{ type: 'string' }],
    'arg': [{ type: 'string' }],
    'image': [{ type: 'path' }],
    'label': [{ type: 'string' }],
  },
  'app': {
    'app': [{ type: 'string' }],
    'config': [{ type: 'json' }],
  },
};
// data modifier
const dataModifier = {
  command: (d) => {
    command = d.command.split(' ');
    d.command = command;
  },
  deck_command: (d) => {
    d[d.deck_command] = d.arg
    delete (d['deck_command'])
    delete (d['arg'])
  },
  chrome: (d) => {
    if (!d.image || d.image === '') {
      delete (d['image'])
    }
  },
};

const Modal = {
  data() {
    return {
      settingData: {},
      images: [],
      apps: [],
      checkResult: {},
      settingType: null,
      iconImage: null,
      target_page: null,
    }
  },
  emits: ['initializeModal'],
  props: {
    root_dir: String,
    id: String,
    config: Object,
    current_page: String,
    settingTouchscreen: Boolean,
    settingDial: Number,
    settingKey: Number,
    root_dir: String,
  },
  mounted() {
    this.settingData = this.defaultData()
    this.images = this.config.images;
    this.apps = this.config.apps;
    this.target_page = this.current_page;
    let url = "";
    if (this.settingTouchscreen) {
      url = baseURL + 'api/device/' + this.id + '/touchscreen_config/' + this.target_page + '/';
    } else if (this.settingDial) {
      url = baseURL + 'api/device/' + this.id + '/dial_config/' + this.target_page + '/' + this.settingDial + '/';
    } else {
      url = baseURL + 'api/device/' + this.id + '/key_config/' + this.target_page + '/' + this.settingKey + '/';
    }
    axios.get(url).then((response) => {
      const res = response.data;
      if (res.key_config) {
        this.settingType = res.key_config["change_page"] ? "deck_command" : res.key_config["chrome"] ? "chrome" : "command";
        if (this.settingType === "deck_command") {
          this.settingData.deck_command.deck_command = "change_page";
          this.settingData.deck_command.arg = res.key_config["change_page"];
          this.iconImage = this.settingData.deck_command.image = res.key_config["image"];
          this.settingData.deck_command.label = res.key_config["label"];
        } else if (this.settingType === "chrome") {
          this.settingData.chrome.chrome = res.key_config["chrome"];
          this.iconImage = this.settingData.chrome.image = res.key_config["image"];
          this.settingData.chrome.label = res.key_config["label"];
        } else if (this.settingType === "command") {
          this.settingData.command.command = res.key_config["command"].join(" ");
          this.iconImage = this.settingData.command.image = res.key_config["image"];
          this.settingData.command.label = res.key_config["label"];
        }
      } else if (res.app_config) {
        this.settingType = "app";
        this.settingData.app.app = "app" + res.app_config["app"].replace(/([A-Z])/g, '_$1').toLowerCase();
        console.log(this.settingData.app.app)
        delete res.app_config.option["page_key"]
        this.settingData.app.config = JSON.stringify(res.app_config.option, null, 4);
      }
      this.ok = this.fillRequired()
    }
    )
  },
  methods: {
    // default data for settingData.
    defaultData: () => {
      return {
        id: null,
        key: null,
        dial: null,
        root_dir: "",
        target_page: "@HOME",
        for_touchscreen: false,
        for_dial: false,
        chrome: {
          chrome: ['Default', ''],
          image: null,
          label: '',
        },
        command: {
          command: '',
          image: null,
          label: '',
        },
        deck_command: {
          deck_command: '',
          arg: '',
          image: null,
          label: '',
        },
        app: {
          app: '',
          key: null,
          dial: null,
          config: "{}",
        },
        delete: {
          delete: false,
        },
      }
    },
    fillRequired: function () {
      this.checkResult = {};
      const data = this.settingData[this.settingType];
      let valid = true;
      if (required[this.settingType]) {
        const keys = Object.keys(required[this.settingType]);
        for (let i = 0; i < keys.length; i++) {
          let v = required[this.settingType][keys[i]];
          const rule = required[this.settingType][keys[i]];
          if (rule) {
            let result = this.checkRule(keys[i], data[keys[i]], rule);
            if (!result) {
              valid = result;
            }
          }
        }
      }
      return valid;
    },
    checkRule: function (name, data, rule) {
      let valid = true;
      let r = rule[0].type.replace(/\?$/, '');
      let optional = r != rule[0].type;
      if (!rule[0].name) {
        rule[0].name = name;
      }
      this.checkResult[rule[0].name] = optional ? 'yet' : 'valid';
      const invalidString = (data, optional) => {
        return (!optional && !data) || (!optional && typeof (data) !== 'string') || (!optional && data.length === 0);
      }
      if (r === 'json') {
        try {
          JSON.parse(data)
        } catch {
          valid = false;
        }
      } else if (r === 'bool') {
        valid = type(data) === 'boolean';
      } else if (r === 'string') {
        valid = !invalidString(data, optional);
      } else if (r === 'url') {
        if (invalidString(data, optional) || (data && data.length > 0 && !data.match("^https?://.+?\\..+?"))) {
          valid = false;
        }
      } else if (r === 'path') {
        if (invalidString(data, optional) || (data && data.length > 0 && !data.match("^\\.*?(/[\\w \\.\\-\\+]+)+"))) {
          valid = false;
        }
      } else if (r === 'array') {
        if (Array.isArray(data)) {
          for (let i = 0; i < data.length; i++) {
            if (!optional && data[i].length === 0) {
              valid = false;
            }
          }
          if (valid && rule[1] && data.length != rule[1].length) {
            valid = false;
          }
          if (valid) {
            for (let i = 0; i < rule[1].length; i++) {
              let result = this.checkRule(null, data[i], rule[1][i]);
              if (!result) valid = false;
            }
          }
        } else {
          valid = false;
        }
      }
      if (valid) {
        console.log("valid", optional, valid, data, rule);
      } else {
        console.log("invalid", optional, valid, data, rule);
      }
      this.checkResult[rule[0].name] = valid ? 'valid' : 'invalid';
      return valid;
    },
    settingDone: function () {
      let data = this.settingData[this.settingType]
      data.target_page = this.target_page;
      if (dataModifier[this.settingType]) {
        dataModifier[this.settingType](data);
      }
      data.id = this.id;
      data.serial_number = data.serial_number;
      if (this.settingTouchscreen) {
        data.for_touchscreen = true;
      } else if (this.settingDial !== null) {
        data.for_dial = true;
        data.dial = this.settingDial;
      } else {
        data.key = this.settingKey;
      }
      if (data.app) {
        data.app = data.app.replace(/^app_/, '').replace(/_(\w)/g, (_, c) => c.toUpperCase());
        data.app = data.app.charAt(0).toUpperCase() + data.app.slice(1);
        data.config = JSON.parse(data.config)
        axios.post(baseURL + 'api/key_setting/', data);
      } else if (this.settingType === 'delete') {
        data.delete = true
        axios.post(baseURL + 'api/key_setting/', data);
      } else {
        axios.post(baseURL + 'api/key_setting/', data);
      }
      this.$emit('initializeModal', false);
    },
    loadSampleSetting: function () {
      if (this.settingData.app.config === "{}") {
        axios.get(baseURL + 'api/app/' + this.settingData.app.app + '/sample_data/').then((res) => {
          this.settingData.app.config = JSON.stringify(res.data, null, 4);
        });
      }
    },
  },
  template: `
    <h2><template v-if="settingTouchscreen">Touchscreen</template><template v-else-if="settingDial != null">Dial</template><template v-else>Key</template> Setting</h2>
    DeckID: {{ id }} <span v-if="settingTouchscreen">Touchscreen</span><span v-else>/ <template v-if="settingDial != null">Dial: {{ settingDial }}</template><template v-else>Key: {{ settingKey }}</template>
    / Page: {{ current_page }}<br /><br /></span>
    <form id="setting">
      <select
        :value="settingType"
        @change="
          settingType = $event.target.value;
          iconImage = null;
          if (settingType == 'Back') {
            settingType='deck_command';
            settingData.deck_command.deck_command = 'change_page';
            settingData.deck_command.arg = '@previous';
            iconImage = settingData.deck_command.image = root_dir + '/Assets/back.png';
            settingData.deck_command.label = 'Back';
            ok = true;
          } else if (settingType == 'Home') {
              settingType='deck_command';
              settingData.deck_command.deck_command = 'change_page';
              settingData.deck_command.arg = '@HOME';
              iconImage = settingData.deck_command.image = root_dir + '/Assets/home.png';
              settingData.deck_command.label = 'Home';
              ok = true;
            } else if (settingType == 'Game') {
              settingType='deck_command';
              settingData.deck_command.deck_command = 'change_page';
              settingData.deck_command.arg = '@GAME';
              iconImage = settingData.deck_command.image = root_dir + '/Assets/game.png';
              settingData.deck_command.label = 'Game';
              ok = true;
            } else if (settingType == 'delete') {
              settingData = defaultData();
              ok = false;
            }
        "
      >
        <option>select type</option>
        <template v-if="!settingTouchscreen && !settingDial">
          <option value="deck_command">Deck Command</option>
          <option value="Back">Deck Command(Back)</option>
          <option value="Home">Deck Command(Home)</option>
          <option value="Game">Deck Command(Game)</option>
          <option value="chrome">Chrome</option>
          <option value="command">Command</option>
        </template>
        <option value="app">App</option>
        <option value="delete">Delete Setting</option>
      </select>
      <!-- TODO: use component -->
      <div v-if="settingType == 'deck_command'">
        Command:<br />
        <select
          :value="settingData.deck_command.deck_command"
          @change="settingData.deck_command.deck_command = $event.target.value;"
        >
          <option value="">select command</option>
          <option value="change_page">Change Page</option>
        </select><br />
        Deck command argument: <span :class="checkResult.arg"></span><br />
        <input
          type="text"
          value=""
          v-model="settingData.deck_command.arg"
          @input="ok = fillRequired()"
        /><br />
        <div class="icon_image" v-if="iconImage != ''">
          <img :src="iconImage" />
        </div>
        Image Path: <span :class="checkResult.image"></span><br />
        <select
          :value="settingData.deck_command.image"
          @change="
            settingData.deck_command.image = $event.target.value;
            ok = fillRequired();
            if ($event.target.value != '') {
              iconImage = $event.target.value;
            }
          "
        >
          <option value="">select image</option>
          <option v-for="im in images" :value="im">{{ im.replace(/^.+\\//, '') }}</option>
        </select><br />
        Label: <span :class="checkResult.label"></span><br />
        <input
          type="text"
          value=""
          class="label"
          v-model="settingData.deck_command.label"
          @input="ok = fillRequired()"
        />
      </div>
      <div v-if="settingType == 'chrome'">
        Profile: <span :class="checkResult.profile"></span><br />
        <input
          type="text"
          value="Default"
          v-model="settingData.chrome.chrome[0]"
          @input="ok = fillRequired()"
        /><br />
        URL: <span :class="checkResult.url"></span><br />
        <input
          type="text"
          value=""
          class="url"
          v-model="settingData.chrome.chrome[1]"
          @input="ok = fillRequired()"
        /><br />
        Image Path(optional): <span :class="checkResult.image"></span><br />
        <select
          :value="settingData.chrome.image"
          @change="
            settingData.chrome.image = $event.target.value;
            ok = fillRequired();
            if ($event.target.value != '') {
              iconImage = $event.target.value;
            }
          "
        >
          <option value="">select image</option>
          <option v-for="im in images" :value="im">{{ im.replace(/^.+\\//, '') }}</option>
        </select><br />
        Label: <span :class="checkResult.label"></span><br />
        <input
          type="text"
          value=""
          class="label"
          v-model="settingData.chrome.label"
          @input="ok = fillRequired()"
        />
      </div>
      <div v-if="settingType == 'command'">
        Command: <span :class="checkResult.command"></span><br />
        <input
          type="text"
          value=""
          class="path"
          v-model="settingData.command.command"
          @input="ok = fillRequired()"
        /><br />
        Image Path: <span :class="checkResult.image"></span><br />
        <select
          :value="settingData.command.image"
          @change="
            settingData.command.image = $event.target.value;
            ok = fillRequired();
            if ($event.target.value != '') {
              iconImage = $event.target.value;
            }
          "
        >
          <option value="">select image</option>
          <option v-for="im in images" :value="im">{{ im.replace(/^.+\\//, '') }}</option>
        </select><br />
        Label: <span :class="checkResult.label"></span><br />
        <input
          type="text"
          value=""
          class="path"
          v-model="settingData.command.label"
          @input="ok = fillRequired()"
        />
      </div>
      <div v-if="settingType == 'app'">
        App: <span :class="checkResult.app"></span><br />
        <select
          :value="settingData.app.app"
          @change="
            settingData.app.config = '{}';
            settingData.app.app = $event.target.value;
            ok = fillRequired();
            loadSampleSetting();
          "
        >
        <option value="">select app</option>
        <template v-for="app in apps">
          <template v-if="settingTouchscreen === true && app.match('app_touchscreen')">
            <option :value="app">{{ app }}</option>
          </template>
          <template v-if="settingDial !== null && app.match('app_dial')">
            <option :value="app">{{ app }}</option>
          </template>
          <template v-if="!settingTouchscreen && settingDial === null && !app.match('app_dial') && !app.match('app_touchscreen')">
            <option :value="app">{{ app }}</option>
          </template>
        </template>
        </select><br />
        Setting JSON: <span :class="checkResult.config"></span><br />
        <textarea class="setting_json"
        v-model="settingData.app.config"
        @input="ok = fillRequired()"
        ></textarea>
      </div>
      <div v-if="settingType == 'delete'">
        <p>Are you sure to delete this setting?</p>
        <input type="button" value="Delete" @click.left="settingDone()" />
      </div>        
      <div v-if="settingType != null && ok">
        <input type="button" value="SAVE" @click.left="settingDone()" />
      </div>
    </form>
    `
};
