import { useLocation, useParams } from 'react-router-dom'
import { StudentProfileView } from '../../components/StudentProfileView'

export default function StudentProfilePage() {
  const { id } = useParams()
  const location = useLocation()
  const backTo = location.state?.from || '/admin/students'
  const backLabel = location.state?.fromLabel || 'Back to students'
  return <StudentProfileView studentId={id} backTo={backTo} backLabel={backLabel} allowTransfer allowEdit />
}
