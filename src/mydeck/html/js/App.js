const baseURL = location.href.replace(location.hash, "");
const page = location.hash.replace("#", "");
const id2sn = {};
const App = {
    data() {
        return {
            page: page || "home",
            items: [],
            images: [],
        }
    },
    mounted() {
        axios.get(baseURL + "api/images").then((res) => {
            const images = res.data;

            axios.get(baseURL + "api/apps").then((res) => {
                const apps = res.data;

                axios.get(baseURL + "api/device_info").then((res) => {
                    // console.log(res)
                    const keys = Object.keys(res.data).sort()
                    keys.forEach((i, v) => {
                        id2sn["app" + i] = res.data[i]["serial_number"];
                    });
                    console.log(id2sn);
                    const items = [];
                    keys.forEach((i, v) => {
                        items.push({
                            ok: false,
                            serial_number: id2sn['app' + i],
                            modal_block_class: 'off',
                            images: images,
                            apps: apps,
                            iconImage: "",
                            key_count: [],
                            items: {},
                            id: i,
                            checkResult: {},
                            deviceInfo: res.data[i],
                            columns: res.data[i].columns,
                            dials: res.data[i].dials,
                            dial_states: res.data[i].dial_states,
                            has_touchscreen: res.data[i].has_touchscreen,
                            touchscreen_size: res.data[i].touchscreen_size,
                            settingMode: false,
                            settingKey: 0,
                            settingType: null,
                            dialChanged: 0,
                        })
                    });
                    this.items = items;
                }).catch((error) => {
                    console.error('APIからのデータ取得中にエラーが発生しました:', error);
                });
            });
        });
    },
    template: `
            <div id="container">
                <div id="header-menu" class="header-menu" v-if="!page.match('^full-device')">
                    <strong>MyDeck</strong>
                    <div class="dropdown">
                        <a class="dropbtn">Decks</a>
                        <div class="dropdown-content">
                            <a @click="page=1" href="/">All Decks</a>
                            <hr class="separator" />
                            <template v-for="config in items" :key="config.id">
                                <a @click="page='device-' + config.id" :href="'#device-' + config.id">{{config.id}}: {{config.serial_number}}</a>
                            </template>
                        </div>
                    </div>
                    <div class="dropdown">
                        <a class="dropbtn">APIs</a>
                        <div class="dropdown-content">
                            <a target="_blank" href="/api/device_info">DeviceInfo API &#x29c9;</a>
                            <a target="_blank" href="/api/status">Status API &#x29c9;</a>
                            <a target="_blank" href="/api/images">Asset Images API &#x29c9;</a>
                            <a target="_blank" href="/api/apps">Apps API &#x29c9;</a>
                            <a target="_blank" href="/api/games">Games API &#x29c9;</a>
                            <a target="_blank" href="/api/device_key_images">Devices' images API &#x29c9;</a>
                            <a target="_blank" href="/api/resource">Resouse API &#x29c9;</a>
                        </div>
                    </div>
                    <div class="dropdown">
                        <a class="dropbtn">?</a>
                        <div class="dropdown-content">    
                        <a @click="page='help'" href="/#help">Help</a>
                        <a target="_blank" href="/chart/status">Status Chart &#x29c9;</a>
                        <a target="_blank" href="https://github.com/ktat/mydeck/">GitHub &#x29c9;</a>
                        </div>
                    </div>
                </div>
                <div :id="'app-container'+ (page.match('^full-device') ? '-full' : '')">
                    <div v-if="page === 'help'">
                        <help />
                    </div>
                    <div v-else-if="page.match(/^(full-)?device-/)">
                        <template v-for="config in items" :key="config.id">
                            <div v-if="'device-' + config.id === page" class="mydeck">
                                <mydeck :config="config" />
                            </div>
                            <div v-else-if="'full-device-' + config.id === page" class="mydeck">
                                <mydeck :config="config" :full="true" />
                            </div>
                        </template>
                    </div>
                    <div v-else>
                        <div v-for="config in items" :key="config.id" class="mydeck">
                            <mydeck :config="config" />
                        </div>
                    </div>
                </div>                        
            </div>
        `
};