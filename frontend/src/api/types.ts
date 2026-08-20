export type Role = 'owner' | 'manager' | 'scanner'

export type TicketStatus =
  | 'registered'
  | 'checked_in'
  | 'called'
  | 'serving'
  | 'done'
  | 'skipped'
  | 'cancelled'

export type EventPhase =
  | 'closed'
  | 'announced'
  | 'registration'
  | 'checkin'
  | 'queue'
  | 'hold'
  | 'ended'

export interface User {
  id: number
  phone: string
  first_name: string
  last_name: string
  role: Role
  company_id: number | null
  branch_id: number | null
  is_active: boolean
}

export interface Branch {
  id: number
  name: string
  address: string
  desk_count: number
  employee_count: number
}

export interface CompanyBot {
  id: number
  username: string | null
}

export interface TokenResponse {
  access_token: string
  user: User
}

export interface CompanyPhone {
  id: number
  phone: string
  label: string
}

export interface CompanyLocation {
  id: number
  name: string
  address: string
  map_url: string
}

export interface Company {
  id: number
  name: string
  logo_url: string | null
  bots: CompanyBot[]
  max_bots: number
  telegram_bot_username: string | null
  has_bot_token: boolean
  phones: CompanyPhone[]
  locations: CompanyLocation[]
}

export interface EmployeeWithPassword {
  employee: User
  password: string
}

export interface Desk {
  id: number
  number: number
  name: string
  manager_id: number | null
  manager_name: string | null
  branch_id: number | null
  branch_name: string | null
}

export interface EventBranch {
  id: number
  name: string
}

export interface SaleEvent {
  id: number
  name: string
  registration_starts_at: string
  starts_at: string
  checkin_until: string
  sale_starts_at: string
  sale_hold: boolean
  sale_ended_at: string | null
  is_active: boolean
  display_code: string
  phase: EventPhase
  branches: EventBranch[]
  ticket_count: number
  checked_in_count: number
}

export interface Ticket {
  id: number
  number: string
  code: string
  first_name: string
  last_name: string
  phone: string
  status: TicketStatus
  late: boolean
  source: 'bot' | 'staff' | 'seed'
  branch_id: number | null
  branch_name: string | null
  registered_at: string
  checked_in_at: string | null
  called_at: string | null
  desk_number: number | null
  position: number | null
  call_count: number
  skip_count: number
}

export interface StaffTicketView {
  id: number
  number: string
  name: string
  phone: string
  status: TicketStatus
  late: boolean
  branch_id: number | null
  branch_name: string | null
  desk_id: number | null
  desk_number: number | null
  called_at: string | null
  registered_at: string
  skip_count: number
  position: number | null
}

export interface QueueStats {
  registered: number
  arrived: number
  waiting: number
  done: number
  skipped: number
  /** clients who joined the end-of-day (last) queue */
  late: number
  /** walk-ins added at the door by the owner/scanner */
  staff_added: number
}

/** One waiting ticket as the public TV board shows it: the 4-letter code,
 * the client's name and the exact bot registration moment (with ms). */
export interface QueueNextEntry {
  number: string
  name: string
  registered_at: string
  late: boolean
}

export interface BranchQueueState {
  id: number
  name: string
  next: QueueNextEntry[]
  stats: QueueStats
}

export interface PublicState {
  type: 'state'
  event: {
    id: number
    name: string
    phase: EventPhase
    registration_starts_at: string
    starts_at: string
    checkin_until: string
    sale_starts_at: string
    sale_hold: boolean
    sale_ended_at: string | null
    company_name: string
    logo_url: string | null
    branches: EventBranch[]
  }
  now: string
  call_timeout_minutes: number
  called: {
    number: string
    name: string
    desk_number: number | null
    branch_id: number | null
    status: TicketStatus
    called_at: string | null
  }[]
  next: QueueNextEntry[]
  by_branch: BranchQueueState[]
  stats: QueueStats
}

export interface StaffState extends PublicState {
  waiting_list: StaffTicketView[]
  active: StaffTicketView[]
}

export interface CheckinResponse {
  ok: boolean
  kind: 'arrived' | 'late' | 'already' | 'called' | 'serving' | 'done' | 'cancelled'
  message: string
  ticket: Ticket
}

export interface ActionResponse {
  ok: boolean
  message: string
  ticket: Ticket | null
}

export interface WalkinResponse {
  ok: boolean
  message: string
  ticket: Ticket
  /** the new client's QR as a data URL — shown once after adding */
  qr: string
}

export interface StatsDaily {
  day: string
  label: string
  registered: number
  arrived: number
  served: number
}

export interface StatsEventRow {
  id: number
  name: string
  // an event may run in several branches
  branch_names: string[]
  starts_at: string
  registered: number
  arrived: number
  served: number
  skipped: number
}

export interface StatsBranchRow {
  id: number
  name: string
  events: number
  registered: number
  arrived: number
  served: number
}

export interface StatsOverview {
  days: number
  totals: {
    registered: number
    arrived: number
    served: number
    skipped: number
    cancelled: number
    late: number
    events: number
  }
  avg_wait_minutes: number | null
  avg_service_minutes: number | null
  daily: StatsDaily[]
  hourly: { hour: number; registered: number }[]
  events: StatsEventRow[]
  branches: StatsBranchRow[]
}

export interface PublicTicket {
  number: string
  first_name: string
  status: TicketStatus
  late: boolean
  position: number | null
  waiting_count: number
  desk_number: number | null
  branch_name: string | null
  branch_address: string | null
  qr: string
  event: {
    name: string
    phase: EventPhase
    starts_at: string
    checkin_until: string
  }
}
