export type WorkerRole = 'staff' | 'manager'

export interface CurrentUser {
  id: number
  username: string
  role: WorkerRole | null
}

export type TableStatus = 'free' | 'reserved' | 'occupied' | 'cleaning'

export interface RestaurantTable {
  id: number
  identifier: string
  capacity: number
  status: TableStatus
  location: 'any' | 'indoor' | 'outdoor'
  seating_type: 'standard' | 'booth' | 'bar'
  has_accessibility: boolean
  can_accommodate_high_chair: boolean
}

export type WaitlistStatus =
  | 'waiting'
  | 'notified'
  | 'arrived'
  | 'seated'
  | 'late_demoted'
  | 'cancelled'
  | 'no_show'
  | 'left'

export interface WaitlistEntry {
  id: number
  guest_name: string
  party_size: number
  public_identifier: string
  estimated_wait_minutes: number
  contact_text: string
  preference_notes: string
  status: WaitlistStatus
  assigned_table: RestaurantTable | null
  checked_in_at: string
  notified_at: string | null
  arrived_at: string | null
  seated_at: string | null
  cancelled_at: string | null
  no_show_at: string | null
  left_at: string | null
}

export interface WaitlistResponse {
  status_filter: 'all' | 'waiting'
  entries: WaitlistEntry[]
  free_tables: RestaurantTable[]
  eligible_entries: WaitlistEntry[]
}

export interface TableStatusGroup {
  status: TableStatus
  label: string
  tables: (RestaurantTable & { current_guest_entry: WaitlistEntry | null })[]
}

export interface TableStatusResponse {
  status_groups: TableStatusGroup[]
  eligible_entries: WaitlistEntry[]
  free_tables: RestaurantTable[]
}

export interface EtaRule {
  id: number
  min_party_size: number
  max_party_size: number | null
  estimated_wait_minutes: number
  is_active: boolean
}

export interface RestaurantSettings {
  grace_period_minutes: number
}

export interface Worker {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  is_active: boolean
  role: WorkerRole
}

export interface GuestStatus extends WaitlistEntry {
  can_cancel: boolean
  show_table_ready_message: boolean
  cancellation_blocked?: boolean
}

export type FieldErrors = Record<string, string[]>
