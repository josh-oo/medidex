// Lets other parts of the UI (e.g. extensions) fill the "Relevant Studies" search box and run it.
const EVENT_NAME = "medidex:study-search-request"

export function requestStudySearch(query: string): void {
  window.dispatchEvent(new CustomEvent<string>(EVENT_NAME, { detail: query }))
}

export function onStudySearchRequest(handler: (query: string) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<string>).detail)
  window.addEventListener(EVENT_NAME, listener)
  return () => window.removeEventListener(EVENT_NAME, listener)
}
