const Help = {
    data() {
        return {};
    },
    template: `
            <div id="help-container">
                <h1>Help</h1>
                <ul>
                    <li><a href="#put-image">How to use your own image for button?</a></li>
                    <li><a href="#configure-button">How to configure button/touchscreen/dial?</a></li>
                    <li><a href="#add-games">How to add games?</a></li>
                </ul>
                <h2 id="put-image">How to use your own image for button?</h2>
                <ol>
                    <li>Prepare your own PNG images.</li>
                    <li>Put your images to Assets directory in your configuration path(default is ~/.config/mydeck/).</li>
                </ol>
                <h2 id="configure-button">How to configure button/touchscreen/dial?</h2>
                <ol>
                    <li>right click the button/touchscreen/dial which you want to change.</li>
                    <li>setting modal is opend</li>
                    <li>select the type
                        <ul>
                            <li>Deck Command ... Currently &quot;Change Page&quot; only</li>
                            <li>Chrome ... Open chrome browser</li>
                            <li>Command ... Execute command</li>
                            <li>App ... choose the application you want to run on the target</li>
                            <li>Delete Setting ... delete setting & app from the target</li>
                        </ul>
                    </li>
                </ol>
                <h3>Type: Deck Command</h3>
                <ol>
                    <li>Select Command</li>
                    <p>Choose &quot;Change Page&quot;</p>
                    <li>Deck commnad argument</li>
                    <p>Any string is OK which express the page name.</p>
                    <li>Image Path</li>
                    <p>Choose an image from dropdown list.</p>
                    <li>Label</li>
                    <p>Any string is OK. It is shown as button label.</p>
                </ol>
                <h3>Type: Chrome</h3>
                <ol>
                    <li>Profile</li>
                    <p>Choose a profile of Chrome.</p>
                    <li>URL</li>
                    <p>URL which you want to open.</p>
                    <li>Image Path(optional)</li>
                    <p>Choose an image from dropdown list. If you don't choose, use favicon of the URL.</p>
                    <li>Label</li>
                    <p>Any string is OK. It is shown as button label.</p>
                </ol>
                <h3>Type: Command</h3>
                <ol>
                    <li>Command</li>
                    <p>Command which you want to execute.</p>
                    <li>Image Path</li>
                    <p>Choose an image from dropdown list.</p>
                    <li>Label</li>
                    <p>Any string is OK. It is shown as button label.</p>
                </ol>
                <h3>Type: App</h3>
                <ol>
                    <li>App</li>
                    <p>Choose an application from dropdown list.</p>
                    <li>JSON</li>
                    <p>JSON string which is passed to the application.</p>
                </ol>
                <h3>Type: Delete Setting</h3>
                <ol>
                    <li>Delete Setting</li>
                    <p>Push "Delete" Button, then the setting is deleted.</p>
                </ol>
            </div>
            <h2 id="add-games">How to add games?</h2>
        `
};
