import { useParams } from 'react-router-dom'
import { StudentProfileView } from '../../components/StudentProfileView'

export default function StudentProfilePage() {
  const { id } = useParams()
  return <StudentProfileView studentId={id} backTo="/trainer/my-students" backLabel="Back to my students" />
}
