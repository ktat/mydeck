from mydeck import HookAppBase

class AppSyncDeckPage(HookAppBase):
    """Open the same name page of current page of deck on other decks."""
    on = 'page_change_any'

    def execute_on_hook(self) -> None:
        page = self.mydeck.current_page()
        for other_deck in self.mydeck.mydecks.list_other_mydecks(self.mydeck):
            other_deck.set_current_page(page)
