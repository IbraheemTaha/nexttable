import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import type { Worker } from '../../lib/types'

export function WorkerListPage() {
  const [workers, setWorkers] = useState<Worker[]>([])

  useEffect(() => {
    api.get<Worker[]>('/api/workers/').then(setWorkers)
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="page-title">Worker accounts</h1>
        <Link to="/manager/workers/new" className="btn-primary btn-sm">
          Create worker account
        </Link>
      </div>

      <table className="data-table mt-6">
        <thead>
          <tr>
            <th>Username</th>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {workers.map((worker) => (
            <tr key={worker.id}>
              <td className="font-medium text-stone-900">{worker.username}</td>
              <td>
                {worker.first_name} {worker.last_name}
              </td>
              <td>{worker.email}</td>
              <td>{worker.role === 'manager' ? 'Manager' : 'Staff'}</td>
              <td>
                {worker.is_active ? (
                  <span className="badge badge-free">Active</span>
                ) : (
                  <span className="badge badge-left">Inactive</span>
                )}
              </td>
              <td>
                <Link to={`/manager/workers/${worker.id}`} className="link">
                  Edit
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
