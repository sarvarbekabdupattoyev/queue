export type Role = 'owner' | 'manager' | 'scanner'

export type TicketStatus =
  | 'registered'
  | 'checked_in'
  | 'called'
  | 'serving'
  | 'done'
  | 'skipped'
  | 'cancelled'

export type EventPhase = 'closed' | 'registration' | 'checkin' | 'queue'

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
  starts_at: string
  checkin_until: string
  is_active: boolean
  display_code: string
  phase: EventPhase
  branches: EventBranch[]
  ticket_count: number
  checked_in_count: number
}

export interface Ticket {
  id: number
  number: number
  code: string
  first_name: string
  last_name: string
  phone: string
  status: TicketStatus
  late: boolean
  source: 'bot' | 'seed'
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
  number: number
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
}

export interface BranchQueueState {
  id: number
  name: string
  next: number[]
  late_numbers: number[]
  stats: QueueStats
}

export interface PublicState {
  type: 'state'
  event: {
    id: number
    name: string
    phase: EventPhase
    starts_at: string
    checkin_until: string
    company_name: string
    logo_url: string | null
    branches: EventBranch[]
  }
  now: string
  call_timeout_minutes: number
  called: {
    number: number
    desk_number: number | null
    branch_id: number | null
    status: TicketStatus
    called_at: string | null
  }[]
  next: number[]
  late_numbers: number[]
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

export interface PublicTicket {
  number: number
  first_name: string
  status: TicketStatus
  late: boolean
  position: number | null
  waiting_count: number
  desk_number: number | null
  branch_name: string | null
  qr: string
  event: {
    name: string
    phase: EventPhase
    starts_at: string
    checkin_until: string
  }
}
