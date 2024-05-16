const MyDeck = {
  props: {
    config: Object,
    full: Boolean,
    page: String,
  },
  data() {
    return {
      id: this.config.id,
      serial_number: this.config.serial_number,
      items: this.config.items,
      dialChanged: 0,
      settingMode: false,
      settingGameMode: false,
      settingKey: null,
      settingDial: null,
      settingTouchscreen: false,
      target_page: this.current_page,
      deviceInfo: this.config.deviceInfo,
      ok: false,
      modal_block_class: 'off',
      columns: this.config.columns,
      has_touchscreen: this.config.has_touchscreen,
      touchscreen_size: this.config.touchscreen_size,
      baseURL: this.config.baseURL,
      key_count: this.config.key_count
    };
  },
  methods: {
    initializeModal: function (on) {
      if (on) {
        this.settingMode = true;
        this.settingGameMode = false;
        this.modal_block_class = 'on';
      } else {
        this.settingMode = false;
        this.settingGameMode = false;
        this.modal_block_class = 'off';
        this.settingKey = null;
        this.settingDial = null;
        this.settingTouchscreen = false;
      }
      this.ok = false;
    },
    initializeGameModal: function (on) {
      if (on) {
        this.settingMode = false;
        this.settingGameMode = true;
        this.modal_block_class = 'on';
      } else {
        this.initializeModal(false);
      }
      this.ok = false;
    },
    openSettingModal: function (i) {
      if (this.current_page.match(/^~/)) {
        return;
      }

      if (this.current_page === '@GAME') {
        this.initializeGameModal(true);
      } else {
        this.settingKey = i - 1;
        this.settingDial = null;
        this.settingTouchscreen = false;
        this.initializeModal(true);
      }
    },
    openSettingModalDial: function (i) {
      this.settingDial = i - 1;
      this.settingKey = null;
      this.settingTouchscreen = false;
      this.initializeModal(true);
    },
    openSettingModalTouchscreen: function () {
      this.settingTouchscreen = true;
      this.settingKey = null;
      this.settingDial = null;
      this.initializeModal(true);
    },
    loadData: function () {
      axios.get(baseURL + 'api/' + this.config.id).then(
        (response) => {
          if (this.items.data) {
            this.root_dir = this.items.data.root_dir;
            this.current_page = this.items.data.current_page;
            let currentDialStates = this.items.data.dial_states;
            let nextDialStates = this.config.deviceInfo.dial_states;
          }
          if (this.dialChanged === 0) {
            this.key_count = this.config.deviceInfo.key_count;
            this.items = response;
          }
        })
    },
    closeSettingModal: function () {
      this.initializeModal(false);
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
      <h1 v-if="!full">Deck {{ config.id }} (sn: {{ config.serial_number }}) <a target="_blank" :href="'#full-device-'+config.id" title="Open this deck in new tab">&#x29c9;</a></h1>
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
            @click.right.prevent="openSettingModalTouchscreen()"
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
            :value="items.data.dial_states[i-1]"
            class="slider"
            id="myRange"
            v-on:mousedown="dialChanged = 1"
            v-on:mouseup="dialChanged = 0"
            @click.right.prevent="openSettingModalDial(i)"
            :onchange="
              'changeDial(this, &quot;' + id + '&quot;, ' + (i-1) + ',this.value);'
            "
          />
        </span>
      </span>
      <div v-if="settingGameMode" class="settingGameModal">
        <div id="closeModal" @click.left="closeSettingModal()">&#x274c;</div>
        <game-modal
          :config="config"
          :id="id"
           @initializeModal="initializeModal"
        ></game-modal>
      </div>      
      <div v-if="settingMode" class="settingModal">
        <div id="closeModal" @click.left="closeSettingModal()">&#x274c;</div>
        <modal v-if="settingMode"
         :config="config"
         :id="id"
         :settingKey="settingKey"
         :settingDial="settingDial"
         :settingTouchscreen="settingTouchscreen"
         :current_page="current_page"
         :root_dir="root_dir"
         @initializeModal="initializeModal"
         ></modal>
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
