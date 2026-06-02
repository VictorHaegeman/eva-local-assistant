chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.set({ evaEnabled: true });
});

chrome.action.onClicked.addListener(() => {
  // Popup is defined in manifest; this keeps the service worker alive on click.
});
