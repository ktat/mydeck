// default data for settingData.
const defaultData = () => {
  return {
    id: null,
    key: null,
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
  }
};
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

const MyDeck = {
  props: {
    config: Object
  },
  data() {
    return {
      id: this.config.id,
      serial_number: this.config.serial_number,
      items: this.config.items,
      dialChanged: 0,
      settingMode: false,
      settingKey: null,
      settingType: null,
      settingData: this.config.settingData,
      checkResult: {},
      deviceInfo: this.config.deviceInfo,
      ok: false,
      modal_block_class: 'off',
      iconImage: null,
      columns: this.config.columns,
      has_touchscreen: this.config.has_touchscreen,
      touchscreen_size: this.config.touchscreen_size,
      baseURL: this.config.baseURL,
      images: this.config.images,
      key_count: this.config.key_count
    };
  },
  methods: {
    fillRequired: function () {
      this.checkResult = {};
      const data = this.settingData[this.settingType];
      let valid = true;
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
      if (r === 'string') {
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
    openSettingModal: function (i) {
      this.initializeModal();
      this.settingMode = true;
      this.settingKey = i - 1;
      this.modal_block_class = 'on';
    },
    closeSettingModal: function () {
      this.initializeModal();
      this.settingMode = false;
      this.modal_block_class = 'off';
    },
    initializeModal: function () {
      this.settingType = null;
      this.checkResult = {};
      this.settingData = defaultData();
      this.settingKey = null;
      this.ok = false;
    },
    settingDone: function () {
      let data = this.settingData[this.settingType]
      if (dataModifier[this.settingType]) {
        dataModifier[this.settingType](data);
      }
      data.id = this.id;
      data.serial_number = data.serial_number;
      data.key = this.settingKey;
      axios.post(baseURL + 'api/key_setting/', data);
      this.closeSettingModal();
    },
    loadData: function () {
      axios.get(baseURL + 'api/' + this.config.id).then(
        (response) => {
          if (this.items.data) {
            let currentDialStates = this.items.data.dial_states;
            let nextDialStates = this.config.deviceInfo.dial_states;
          }
          if (this.dialChanged === 0) {
            this.key_count = this.config.deviceInfo.key_count;
            this.items = response;
          }
        })
    },
  },
  mounted() {
    this.loadData();
    setInterval(function () {
      this.loadData();
    }.bind(this), 200);
  },
  template: `
    <div
      id="block1"
      :class="modal_block_class"
      @click.left="closeSettingModal()"
    ></div>
    <div class="app">
      <h1>Deck {{ config.id }} (sn: {{ config.serial_number }})</h1>
        <span v-for="i in key_count">
          <img
            :src="'data:image/png;base64,' + items.data.key[i - 1]"
            class="key_image"
            :onclick="'tap(this, &quot;' + id + '&quot;, ' + (i - 1) + ')'"
            @click.right.prevent="openSettingModal(i)"
          />
          <span :class="'mod' + (i % columns)"></span>
      </span>
      <div v-if="items.data">
        <div v-if="has_touchscreen">
          <img
            :src="'data:image/png;base64,' + items.data.touch"
            class="touchscreen"
            :style="{
              width: (touchscreen_size[0] * 595) / 800 + 'px',
              height: (touchscreen_size[1] * 74.375) / 100 + 'px',
            }"
            :onclick="
              'tapScreen(this, &quot;' +
              id +
              '&quot;, event.offsetX, event.offsetY)'
            "
          />
        </div>
      </div>
      <span v-if="items.data">
        <span v-for="i in config.dials">
          <input
            type="range"
            min="0"
            max="100"
            :value="items.data.dial_states[i]"
            class="slider"
            id="myRange"
            v-on:mousedown="dialChanged = 1"
            v-on:mouseup="dialChanged = 0"
            :onchange="
              'changeDial(this, &quot;' + id + '&quot;, ' + i + ',this.value);'
            "
          />
        </span>
      </span>
    <div v-if="settingMode" id="settingModal">
      <div id="closeModal" @click.left="closeSettingModal()">&#x274c;</div>
      <h2>Key Setting</h2>
      DeckID: {{ id }} / Key: {{ settingKey }}<br />
      <form id="setting">
        <select
          @change="
            settingType = $event.target.value;
            iconImage = null;
          "
        >
          <option>select type</option>
          <option value="deck_command">Deck Command</option>
          <option value="chrome">Chrome</option>
          <option value="command">Command</option>
        </select>
        <!-- TODO: use component -->
        <div v-if="settingType == 'deck_command'">
          Command:<br />
          <select
            @change="
              settingData.deck_command.deck_command = $event.target.value
            "
          >
            <option value="">select command</option>
            <option value="change_page">Change Page</option></select
          ><br />
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
            @change="
              settingData.deck_command.image = $event.target.value;
              ok = fillRequired();
              if ($event.target.value != '') {
                iconImage = $event.target.value;
              }
            "
          >
            <option value="">select image</option>
            <option v-for="im in images" :value="im">{{ im }}</option></select
          ><br />
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
            @change="
              settingData.chrome.image = $event.target.value;
              ok = fillRequired();
              if ($event.target.value != '') {
                iconImage = $event.target.value;
              }
            "
          >
            <option value="">select image</option>
            <option v-for="im in images" :value="im">{{ im }}</option></select
          ><br />
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
            @change="
              settingData.command.image = $event.target.value;
              ok = fillRequired();
              if ($event.target.value != '') {
                iconImage = $event.target.value;
              }
            "
          >
            <option value="">select image</option>
            <option v-for="im in images" :value="im">{{ im }}</option></select
          ><br />
          Label: <span :class="checkResult.label"></span><br />
          <input
            type="text"
            value=""
            class="path"
            v-model="settingData.command.label"
            @input="ok = fillRequired()"
          />
        </div>
        <div v-if="settingType != null && ok">
          <input type="button" value="SAVE" @click.left="settingDone()" />
        </div>
      </form>
    </div>
  </div>
  `
}

function tap(e, id, key) {
  setTimeout(() => { buttonOpacity(e, 50) });
  axios.get(baseURL + 'api/' + id + '/' + key);
}

function changeDial(e, id, key, value) {
  axios.get(baseURL + 'api/' + id + '/dial/' + key + '/' + value);
}

function tapScreen(e, id, x, y) {
  x = Math.floor(x * 800 / 595);
  y = Math.floor(y * 100 / 74.375);
  axios.get(baseURL + 'api/' + id + '/touch/' + x + '/' + y);
}

function buttonOpacity(e, o) {
  if (o >= 0) {
    e.style = "opacity: " + o + "%";
    setTimeout(() => { buttonOpacity(e, o - 10) }, 25);
  } else {
    e.style = "";
  }
}