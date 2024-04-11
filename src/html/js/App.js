const baseURL = location.href;
const id2sn = {};
const App = {
    data() {
        return {
            page: 1,
            items: [],
            images: [],
        }
    },
    mounted() {
        axios.get(baseURL + "api/images").then((res) => {
            const images = res.data;
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
    },
    template: `
            <div id="container">
                <div id="header-menu" class="header-menu">
                    <strong>MyDeck</strong>
                    <div class="dropdown">
                        <a class="dropbtn" @click="page=1">Decks</a>
                    </div>
                    <div class="dropdown">
                        <a class="dropbtn">APIs</a>
                        <div class="dropdown-content">
                            <a target="_blank" href="/api/status">Status JSON &#x29c9;</a>
                            <a target="_blank" href="/api/device_info">DeviceInfo JSON &#x29c9;</a>
                            <a target="_blank" href="/api/images">images JSON &#x29c9;</a>
                            <a target="_blank" href="/api/device_key_images">Devices and its images JSON &#x29c9;</a>
                            <a target="_blank" href="/api/resource">Resouse JSON &#x29c9;</a>
                        </div>
                    </div>
                    <div class="dropdown">
                        <a class="dropbtn">Status Chart</a>
                        <div class="dropdown-content">    
                            <a target="_blank" href="/chart/status">Status Chart &#x29c9;</a>
                        </div>
                    </div>
                    <div class="dropdown">
                        <a class="dropbtn">?</a>
                        <div class="dropdown-content">    
                        <a @click="page=2">help</a>
                        <a target="_blank" href="https://github.com/ktat/mydeck">GitHub &#x29c9;</a>
                        </div>
                    </div>
                </div>
                <div id="app-container">
                    <div v-if="page === 1">
                            <div v-for="config in items" :key="config.id" class="mydeck">
                                <mydeck :config="config" />
                        </div>
                    </div>
                    <div v-if="page === 2">
                        <help />
                    </div>
                </div>                        
            </div>
        `
};