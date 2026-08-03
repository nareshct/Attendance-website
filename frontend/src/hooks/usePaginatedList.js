import { useCallback, useState } from 'react'
import { useApi } from './useApi'

// Backs a list page's "Load more" / "Load less" controls on top of a paginated list
// endpoint (see DEFAULT_PAGINATION_CLASS in backend/config/settings.py). `reload()`
// (re)fetches from page 1 — call it on mount and after any action that should refresh the
// list. `loadMore()` appends the next page. `loadLess()` collapses back down to page 1.
//
// Note for callers that also do client-side search/filtering on `items`: search only
// covers what's been loaded so far, not the whole server-side list, until "Load more" is
// used — the same trade-off every "load more" list in this pattern makes.
export function usePaginatedList(path) {
  const api = useApi()
  const [items, setItems] = useState([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  // Only reflects the very first load — never re-flips true on later reloads/refreshes,
  // so an action like "Archive" refreshing the list doesn't flash the table back to a
  // loading state.
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)

  const fetchPage = useCallback(
    (pageNum) => {
      const separator = path.includes('?') ? '&' : '?'
      return api(`${path}${separator}page=${pageNum}`, { raw: true })
    },
    [api, path],
  )

  const reload = useCallback(async () => {
    try {
      const data = await fetchPage(1)
      setItems(data.results)
      setCount(data.count)
      setHasMore(Boolean(data.next))
      setPage(1)
      return data.results
    } finally {
      setLoading(false)
    }
  }, [fetchPage])

  const loadMore = useCallback(async () => {
    setLoadingMore(true)
    try {
      const data = await fetchPage(page + 1)
      setItems((prev) => [...prev, ...data.results])
      setHasMore(Boolean(data.next))
      setPage(page + 1)
    } finally {
      setLoadingMore(false)
    }
  }, [fetchPage, page])

  const loadLess = useCallback(() => reload(), [reload])

  return { items, setItems, count, page, hasMore, loading, loadingMore, reload, loadMore, loadLess }
}
