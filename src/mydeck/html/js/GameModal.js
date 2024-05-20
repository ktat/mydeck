const GameModal = {
    data() {
        return {
            settingData: {},
            games: [],
            gamesCopy: [],
            start: null,
            over: null,
        };
    },
    emits: ['initializeModal'],
    props: {
        config: Object,
        id: String,
    },
    mounted() {
        const url = baseURL + 'api/device/' + this.id + '/game_config/';
        axios.get(url).then((response) => {
            havingGame = {};
            const res = response.data;
            idx = 0;
            for (const game of res) {
                havingGame[game.game] = idx;
                game.enabled = true;
                game.draggable = true;
                this.games.push(game)
                idx++;
            }

            const url = baseURL + 'api/games';
            axios.get(url).then((response) => {
                const res = response.data;
                const games = res;
                for (const game of games) {
                    gameName = game.name.replace(/_(.)/g, (match, p1) => p1.toUpperCase()).replace(/^game/, "");
                    if (havingGame[gameName] !== undefined) {
                        this.games[havingGame[gameName]].mode_explanation = game.mode_explanation;
                        continue;
                    }
                    this.games.push({
                        "game": gameName,
                        "enabled": false,
                        "draggable": true,
                        "mode_explanation": game.mode_explanation,
                    });
                }
            });
        });
    },
    methods: {
        toggleEnabled(index) {
            this.games[index].enabled = !this.games[index].enabled;
            if (this.games[index].enabled && !this.games[index].expanded) {
                this.toggleAccordion(index);
            } else if (!this.games[index].enabled && this.games[index].expanded) {
                this.toggleAccordion(index);
            }
        },
        toggleAccordion(index) {
            this.games[index].expanded = !this.games[index].expanded;
            let idx = 0
            for (game of this.games) {
                if (idx !== index) {
                    game.expanded = false;
                }
                idx++;
            }
        },
        dragStart(event, index) {
            this.start = index
            event.dataTransfer.effectAllowed = 'move';
        },
        dragOver(event, index) {
            this.over = index
        },
        dragEnd(event) {
            const start = this.start;
            const target = this.over;
            if (start == undefined || target == undefined || start === target) {
                return;
            }

            let idx = 0;
            const copyGames = [];
            for (game of this.games) {
                if (idx != start) {
                    if (idx == target) {
                        if (start < target) {
                            copyGames.push(this.games[target]);
                            copyGames.push(this.games[start]);
                        } else {
                            copyGames.push(this.games[start]);
                            copyGames.push(this.games[target]);
                        }
                    } else {
                        copyGames.push(this.games[idx]);
                    }
                }
                idx++;
            }
            this.games = copyGames;
        },
        settingDone() {
            const url = baseURL + 'api/key_setting/';
            const data = { "id": this.id, "games": [] };
            for (game of this.games) {
                if (game.enabled) {
                    const d = {
                        "game": game.game
                    }
                    if (game.modes && game.modes !== "") {
                        d.modes = JSON.parse("[" + game.modes + "]")
                    }
                    data.games.push(d)
                }
            }
            axios.post(url, data).then((response) => {
                this.$emit('initializeModal', false);
            });
        }
    },
    template: `
        <h2>Game Setting</h2>
        Drag & drop to change the order of games.<br />
        <template v-for="(game, index) in games" :key="game.game">
            <div
                class="game-draggable"
                :draggable="game.draggable"
                @dragstart="dragStart($event, index)"
                @dragover="dragOver($event,index)"
                @dragend="dragEnd($event)"
            >
                <div>
                    <label><input @click="toggleEnabled(index)" v-model="game.enabled" type="checkbox">
                    {{ game.game }}</label>
                    <span class="toggle-game-mode-editor" v-if="game.mode_explanation != ''" @click="toggleAccordion(index)">
                        <span v-if="game.expanded"  >^</span>
                        <span v-else="game.expanded">v</span>
                    </span>
                </div>
                <template v-if="game.mode_explanation != ''">
                    <div v-if="game.expanded">
                        <textarea v-model="game.modes" rows="1" cols="50"></textarea><br />
                        <div class="game-mode-explanation">
                        {{ game.mode_explanation }}
                        </div>
                    </div>
                </template>
            </div>
        </template>
        <input type="button" value="SAVE" @click.left="settingDone()" />
    `,
};
