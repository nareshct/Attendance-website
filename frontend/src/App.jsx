import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import { useApi } from './hooks/useApi'
import LoginPage from './pages/LoginPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import ParentSharePage from './pages/ParentSharePage'
import ChangePasswordPage from './pages/ChangePasswordPage'
import AdminDashboard from './pages/admin/AdminDashboard'
import StudentsPage from './pages/admin/StudentsPage'
import StudentProfilePage from './pages/admin/StudentProfilePage'
import TrainersPage from './pages/admin/TrainersPage'
import TrainerDetailPage from './pages/admin/TrainerDetailPage'
import ClientsPage from './pages/admin/ClientsPage'
import ClientDetailPage from './pages/admin/ClientDetailPage'
import CoursesPage from './pages/admin/CoursesPage'
import CourseMaterialsPage from './pages/admin/CourseMaterialsPage'
import EnrollmentsPage from './pages/admin/EnrollmentsPage'
import BatchesPage from './pages/admin/BatchesPage'
import BatchDetailPage from './pages/admin/BatchDetailPage'
import AttendanceRequestsPage from './pages/admin/AttendanceRequestsPage'
import PayoutsPage from './pages/admin/PayoutsPage'
import ReportsPage from './pages/admin/ReportsPage'
import ActivityLogPage from './pages/admin/ActivityLogPage'
import TrainerDashboard from './pages/trainer/TrainerDashboard'
import MyStudentsPage from './pages/trainer/MyStudentsPage'
import MarkAttendancePage from './pages/trainer/MarkAttendancePage'
import MyEarningsPage from './pages/trainer/MyEarningsPage'
import TrainerCourseMaterialsPage from './pages/trainer/CourseMaterialsPage'
import TrainerStudentProfilePage from './pages/trainer/StudentProfilePage'
import TrainerBatchesPage from './pages/trainer/BatchesPage'

const ADMIN_NAV = [
  { to: '/admin', label: 'Dashboard', end: true },
  { to: '/admin/students', label: 'Students' },
  { to: '/admin/trainers', label: 'Trainers' },
  { to: '/admin/clients', label: 'Clients' },
  { to: '/admin/courses', label: 'Courses' },
  { to: '/admin/course-materials', label: 'Course Materials' },
  { to: '/admin/enrollments', label: 'Enrollments' },
  { to: '/admin/batches', label: 'Batches' },
  { to: '/admin/attendance-requests', label: 'Attendance Requests' },
  { to: '/admin/payouts', label: 'Payouts' },
  { to: '/admin/reports', label: 'Reports' },
  { to: '/admin/activity-log', label: 'Activity Log' },
]

const TRAINER_NAV = [
  { to: '/trainer', label: 'Dashboard', end: true },
  { to: '/trainer/my-students', label: 'My Students' },
  { to: '/trainer/mark-attendance', label: 'Mark Attendance' },
  { to: '/trainer/my-batches', label: 'My Batches' },
  { to: '/trainer/my-earnings', label: 'My Earnings' },
  { to: '/trainer/course-materials', label: 'Course Materials' },
]

function TrainerShell() {
  const api = useApi()
  const [hasBatches, setHasBatches] = useState(true)

  useEffect(() => {
    let cancelled = false
    api('/api/my-batches/')
      .then((batches) => {
        if (!cancelled) setHasBatches(batches.length > 0)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [api])

  const navItems = hasBatches ? TRAINER_NAV : TRAINER_NAV.filter((item) => item.to !== '/trainer/my-batches')

  return <Layout title="Trainer" navItems={navItems} accentClass="bg-brand-violet" />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/reset-password/:uid/:token" element={<ResetPasswordPage />} />
        <Route path="/parent/:token" element={<ParentSharePage />} />

        <Route
          path="/admin"
          element={
            <ProtectedRoute role="admin">
              <Layout title="Admin" navItems={ADMIN_NAV} accentClass="bg-navy" />
            </ProtectedRoute>
          }
        >
          <Route index element={<AdminDashboard />} />
          <Route path="students" element={<StudentsPage />} />
          <Route path="students/:id" element={<StudentProfilePage />} />
          <Route path="trainers" element={<TrainersPage />} />
          <Route path="trainers/:id" element={<TrainerDetailPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/:id" element={<ClientDetailPage />} />
          <Route path="courses" element={<CoursesPage />} />
          <Route path="course-materials" element={<CourseMaterialsPage />} />
          <Route path="enrollments" element={<EnrollmentsPage />} />
          <Route path="batches" element={<BatchesPage />} />
          <Route path="batches/:id" element={<BatchDetailPage />} />
          <Route path="attendance-requests" element={<AttendanceRequestsPage />} />
          <Route path="payouts" element={<PayoutsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="activity-log" element={<ActivityLogPage />} />
          <Route path="change-password" element={<ChangePasswordPage />} />
        </Route>

        <Route
          path="/trainer"
          element={
            <ProtectedRoute role="trainer">
              <TrainerShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<TrainerDashboard />} />
          <Route path="my-students" element={<MyStudentsPage />} />
          <Route path="students/:id" element={<TrainerStudentProfilePage />} />
          <Route path="mark-attendance" element={<MarkAttendancePage />} />
          <Route path="my-batches" element={<TrainerBatchesPage />} />
          <Route path="my-earnings" element={<MyEarningsPage />} />
          <Route path="course-materials" element={<TrainerCourseMaterialsPage />} />
          <Route path="change-password" element={<ChangePasswordPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  )
}
