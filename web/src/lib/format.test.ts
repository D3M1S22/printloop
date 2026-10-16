import approved from '../../fixtures/case_approved.json'
import awaiting from '../../fixtures/case_awaiting_approval.json'
import created from '../../fixtures/case_created.json'
import done from '../../fixtures/case_done.json'
import type { Case } from '../api/types'
import { delta, duration, num } from './format'
import { currentStep } from './loop'

describe('format', () => {
  it('formatta numeri e unità', () => {
    expect(num(0.95, 'x')).toBe('0,95×')
    expect(num(80, 'mm/s')).toBe('80 mm/s')
    expect(num(null)).toBe('—')
  })

  it('formatta durate', () => {
    expect(duration(703.6)).toBe('11 min 44 s')
    expect(duration(4683)).toBe('1 h 18 min')
    expect(duration(null)).toBe('—')
  })

  it('descrive le variazioni', () => {
    expect(delta([703.6, 713.9], 'time')).toBe('+10 s')
    expect(delta([4.39, 4.39], 'grams')).toBe('invariato')
    expect(delta([3.72, 3.59], 'grams')).toBe('−0,13 g')
  })
})

describe('currentStep', () => {
  it('segue lo stato del caso', () => {
    expect(currentStep(created as unknown as Case)).toBe(0)
    expect(currentStep(awaiting as unknown as Case)).toBe(3)
    expect(currentStep(approved as unknown as Case)).toBe(4) // seconda iterazione: ristampa
    expect(currentStep(done as unknown as Case)).toBe(5)
  })
})
