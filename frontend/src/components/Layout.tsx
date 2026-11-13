import type { ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { useLogout } from '../queries.ts'

type NavItem = { to: string; label: string; end?: boolean; icon: ReactNode }

function icon(path: string): ReactNode {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  )
}

const links: NavItem[] = [
  { to: '/', label: 'Home', end: true, icon: icon('M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z') },
  { to: '/practice', label: 'Practice', icon: icon('M8 5.5v13l11-6.5z') },
  { to: '/exams', label: 'Exams', icon: icon('M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5') },
  { to: '/subjects', label: 'Subjects', icon: icon('M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11') },
  {
    to: '/settings',
    label: 'Settings',
    icon: icon('M5 7h9M18 7h1M5 17h1M10 17h9M16 5v4M8 15v4'),
  },
]

/**
 * The frame around every page. On a wide screen the sections are links in the
 * top bar; on a phone they are a tab bar at the bottom, within reach of a thumb.
 */
export function Layout() {
  const logout = useLogout()
  // The review screen puts tasks and their page side by side and needs the room.
  const wide = /^\/exams\/[^/]+$/.test(useLocation().pathname)
  const width = wide ? 'max-w-6xl' : 'max-w-3xl'
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className={`mx-auto flex ${width} items-center gap-1 px-4 pt-[env(safe-area-inset-top)]`}>
          <span className="mr-3 flex min-h-12 items-center text-lg font-semibold tracking-tight text-indigo-600">
            levet
          </span>
          <nav className="hidden flex-1 gap-1 sm:flex" aria-label="Main">
            {links.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex min-h-12 items-center border-b-2 px-3 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-indigo-600 text-indigo-700'
                      : 'border-transparent text-slate-600 hover:text-slate-900'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
            className="hidden min-h-11 shrink-0 rounded-lg px-3 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900 sm:block"
          >
            Log out
          </button>
        </div>
      </header>

      {/* Bottom padding on a phone keeps the last of the page clear of the tab bar. */}
      <main className={`mx-auto ${width} space-y-6 px-4 pt-6 pb-28 sm:pb-8`}>
        <Outlet />
      </main>

      <nav
        className="fixed inset-x-0 bottom-0 z-10 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
        aria-label="Main"
      >
        <ul className="mx-auto flex max-w-md">
          {links.map(({ to, label, end, icon: glyph }) => (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex min-h-14 flex-col items-center justify-center gap-0.5 text-[0.6875rem] font-medium ${
                    isActive ? 'text-indigo-700' : 'text-slate-500'
                  }`
                }
              >
                {glyph}
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}
