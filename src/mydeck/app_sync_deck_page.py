from mydeck import HookAppBase

class AppSyncDeckPage(HookAppBase):
    on = 'page_change_any'
    """Open the same name page of current page of deck on other decks."""

    def execute_on_hook(self):
        page = self.mydeck.current_page()
        for mydeck in self.mydeck.mydecks.list_other_mydecks(self.mydeck):
            mydeck.set_current_page(page)
