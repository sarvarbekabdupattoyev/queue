import { Navigate, Route, Routes } from 'react-router-dom'
import { Suspense, lazy, type ReactNode } from 'react'
import { homeFor, useAuth } from './auth/AuthContext'
import { Spinner } from './components/ui'
import { DashboardLayout } from './components/DashboardLayout'
import type { Role } from './api/types'
import OnboardingPage from './pages/OnboardingPage'
import DashboardHome from './pages/DashboardHome'
import BranchesPage from './pages/BranchesPage'
import EmployeesPage from './pages/EmployeesPage'
import DesksPage from './pages/DesksPage'
import EventsPage from './pages/EventsPage'
import EventDetailPage from './pages/EventDetailPage'
import StatsPage from './pages/StatsPage'
import SettingsPage from './pages/SettingsPage'
import ManagerPage from './pages/ManagerPage'
import ScannerPage from './pages/ScannerPage'
import DisplayPage from './pages/DisplayPage'
import TicketPage from './pages/TicketPage'

// marketing + auth surfaces load on demand (they carry motion); the
// operational app bundle stays lean
const LandingPage = lazy(() => import('./landing/LandingPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))

function Protected({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}

function OwnerArea({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user && user.company_id === null) return <Navigate to="/onboarding" replace />
  return <DashboardLayout>{children}</DashboardLayout>
}

export default function App() {
  const { user, loading } = useAuth()
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Suspense fallback={<Spinner />}>
            <LandingPage />
          </Suspense>
        }
      />
      <Route
        path="/login"
        element={
          <Suspense fallback={<Spinner />}>
            <LoginPage />
          </Suspense>
        }
      />
      <Route
        path="/register"
        element={
          <Suspense fallback={<Spinner />}>
            <RegisterPage />
          </Suspense>
        }
      />
      {/* public screens */}
      <Route path="/display/:displayCode" element={<DisplayPage />} />
      <Route path="/t/:code" element={<TicketPage />} />

      <Route
        path="/onboarding"
        element={
          <Protected roles={['owner']}>
            <OnboardingPage />
          </Protected>
        }
      />
      {(
        [
          ['/dashboard', <DashboardHome />],
          ['/dashboard/events', <EventsPage />],
          ['/dashboard/events/:eventId', <EventDetailPage />],
          ['/dashboard/branches', <BranchesPage />],
          ['/dashboard/stats', <StatsPage />],
          ['/dashboard/employees', <EmployeesPage />],
          ['/dashboard/desks', <DesksPage />],
          ['/dashboard/settings', <SettingsPage />],
        ] as [string, ReactNode][]
      ).map(([path, page]) => (
        <Route
          key={path}
          path={path}
          element={
            <Protected roles={['owner']}>
              <OwnerArea>{page}</OwnerArea>
            </Protected>
          }
        />
      ))}
      <Route
        path="/manager"
        element={
          <Protected roles={['owner', 'manager']}>
            <ManagerPage />
          </Protected>
        }
      />
      <Route
        path="/scanner"
        element={
          <Protected roles={['owner', 'scanner', 'manager']}>
            <ScannerPage />
          </Protected>
        }
      />
      <Route
        path="*"
        element={loading ? <Spinner /> : <Navigate to={user ? homeFor(user.role) : '/'} replace />}
      />
    </Routes>
  )
}
