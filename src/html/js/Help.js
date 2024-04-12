const Help = {
    data() {
        return {
        }
    },
    template: `
        <div id="help-container">
        <h1>Help</h1>
        <h2>How to configure button?</h2>
        <p>1. right click the button which you want to change.</p>
        <p>2. setting modal is opend</p>
        <p>3. select the type</p>
        <ul>
        <li>Deck Command ... Currently &quote;Change Page&quote; only.</li>
        <li>Chrome ... Open chrome browser.</li>
        <li>Command ... Execute command.</li>
        </ul>
        <h3>Type: Deck Command</h3>
        <p>1. Select Command</p>
        Choose &quote;Change Page&quote;
        <p>2. Deck commnad argument</p>
        Any string is OK which express the page name.
        <p>3. Image Path</p>
        Choose an image from dropdown list.
        <p>4. Label</p>
        Any string is OK. It is shown as button label.
        <h3>Type: Chrome</h3>
        <p>1. Profile</p>
        Choose a profile of Chrome.
        <p>2. URL</p>
        URL which you want to open.
        <p>3. Image Path(optional)</p>
        Choose an image from dropdown list. If you don't choose, use favicon of the URL.
        <p>4. Label</p>
        Any string is OK. It is shown as button label.
        <h3>Type: Command</h3>
        <p>1. Command</p>
        Command which you want to execute.
        <p>2. Image Path</p>
        Choose an image from dropdown list.
        <p>3. Label</p>
        Any string is OK. It is shown as button label.
        </div>
    `
}