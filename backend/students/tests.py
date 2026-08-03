from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from .models import Student
from .views import StudentViewSet


class StudentSearchTests(APITestCase):
    """?search= must match name OR student_id server-side (see
    StudentViewSet.search_fields), so a match is found regardless of which
    page it would otherwise fall on — the bug this replaced was client-side
    filtering over only the first loaded page.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_search_student', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        self.target = Student.objects.create(name='Ishani Warrier', grade='5', source_type='B2C')
        Student.objects.create(name='Someone Else', grade='6', source_type='B2C')

    def _search(self, term):
        request = self.factory.get(f'/api/students/?search={term}')
        force_authenticate(request, user=self.admin)
        return StudentViewSet.as_view({'get': 'list'})(request)

    def test_search_by_name_finds_the_student(self):
        response = self._search('warrier')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])

    def test_search_by_student_id_finds_the_student(self):
        response = self._search(self.target.student_id)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])

    def test_search_is_case_insensitive_and_partial(self):
        response = self._search('ISHA')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Ishani Warrier'])


class StudentHardDeleteBlockedTests(APITestCase):
    """Students are only ever archived, never hard-deleted — see
    StudentViewSet.http_method_names and the archive/unarchive actions.
    """

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_student', password='x', is_staff=True)
        student = Student.objects.create(name='Keep Me', grade='5', source_type='B2C')
        factory = APIRequestFactory()

        request = factory.delete(f'/api/students/{student.id}/')
        force_authenticate(request, user=admin)
        response = StudentViewSet.as_view({'delete': 'destroy'})(request, pk=student.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Student.objects.filter(id=student.id).exists())
