const ROLE_HOME = { admin: '/admin', trainer: '/trainer', client: '/client' }

export function roleHome(role) {
  return ROLE_HOME[role] || '/login'
}
