const baseURL = location.href;
const id2sn = {};
const App = {
    data() {
        return {
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
                APIs
                <ul>
                    <li><a href="/api/status">Status JSON</a></li>
                    <li><a href="/api/resource">Resouse JSON</a></li>
                    <li><a href="/api/device_info">DeviceInfo JSON</a></li>
                    <li><a href="/api/images">images JSON</a></li>
                    <li><a href="/api/device_key_images">Devices and its images JSON</a></li>
                </ul>
                Status Chart
                <ul>
                    <li><a href="/chart/status">Status Chart</a></li>
                </ul>
                <div v-for="config in items" :key="config.id">
                    <mydeck :config="config" />
                </div>
            </div>
        `
};