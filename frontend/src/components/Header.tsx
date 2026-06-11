import { NavLink } from 'react-router-dom'
import { useUser } from '../context/UserContext'

export default function Header() {
  const { me } = useUser()
  return (
    <header className="app-header">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <NavLink to="/" aria-label="Home">
        <img className="logo" src="/logo.svg" alt="Tri-State" />
      </NavLink>
      <span className="app-title">Integration Dictionary</span>
      <nav aria-label="Primary">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
          Integrations
        </NavLink>
        <NavLink to="/dag" className={({ isActive }) => (isActive ? 'active' : '')}>
          DAG
        </NavLink>
      </nav>
      <span className="spacer" />
      {me && (
        <div className="user-chip">
          <span className="user-name">{me.user.display_name || me.user.email}</span>
          <span className={`user-role ${me.is_admin ? 'admin' : ''}`}>
            {me.is_admin ? 'Integration team' : 'General user'}
          </span>
        </div>
      )}
    </header>
  )
}
