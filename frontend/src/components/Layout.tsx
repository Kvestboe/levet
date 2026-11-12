import { NavLink, Outlet, useLocation } from 'react-router'
import { useLogout } from '../queries.ts'

const links = [
  { to: '/exams', label: 'Exams' },
  { to: '/subjects', label: 'Subjects' },
]

export function Layout() {
  const logout = useLogout()
  // The review screen puts tasks and their page side by side and needs the room.
  const wide = /^\/exams\/[^/]+$/.test(useLocation().pathname)
  const width = wide ? 'max-w-6xl' : 'max-w-3xl'
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className={`mx-auto flex ${width} items-center gap-1 px-4 pt-[env(safe-area-inset-top)]`}>
          <span className="mr-3 text-lg font-semibold tracking-tight text-indigo-600">levet</span>
          <nav className="flex flex-1 gap-1" aria-label="Main">
            {links.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
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
            className="min-h-11 rounded-lg px-3 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            Log out
          </button>
        </div>
      </header>
      <main className={`mx-auto ${width} space-y-6 px-4 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]`}>
        <Outlet />
      </main>
    </div>
  )
}
