import approved from '../../fixtures/case_approved.json'
import awaiting from '../../fixtures/case_awaiting_approval.json'
import created from '../../fixtures/case_created.json'
import done from '../../fixtures/case_done.json'
import type { Case } from '../api/types'
import { delta, duration, num } from './format'
import { currentStep, iterationTarget, previousStep, stepTarget } from './loop'

describe('format', () => {
  it('formats numbers and units', () => {
    expect(num(0.95, 'x')).toBe('0.95×')
    expect(num(80, 'mm/s')).toBe('80 mm/s')
    expect(num(null)).toBe('—')
  })

  it('formats durations', () => {
    expect(duration(703.6)).toBe('11 min 44 s')
    expect(duration(4683)).toBe('1 h 18 min')
    expect(duration(null)).toBe('—')
  })

  it('describes changes', () => {
    expect(delta([703.6, 713.9], 'time')).toBe('+10 s')
    expect(delta([4.39, 4.39], 'grams')).toBe('unchanged')
    expect(delta([3.72, 3.59], 'grams')).toBe('−0.13 g')
  })
})

describe('currentStep', () => {
  it('follows the case state', () => {
    expect(currentStep(created as unknown as Case)).toBe(0)
    expect(currentStep(awaiting as unknown as Case)).toBe(3)
    expect(currentStep(approved as unknown as Case)).toBe(4) // second iteration: reprint
    expect(currentStep(done as unknown as Case)).toBe(5)
  })
})

describe('rewind targets', () => {
  it('maps stepper columns to the iteration they show', () => {
    const c = approved as unknown as Case // waiting for the reprint photos: columns show iteration 1
    expect(stepTarget(c, 3)).toMatchObject({ iteration: 1, step: 'approval' })
    expect(stepTarget(c, 4)).toBeUndefined()
    expect(previousStep(c)).toMatchObject({ iteration: 1, step: 'approval' })
    expect(iterationTarget(c, 1)).toMatchObject({ step: 'approval' })
  })

  it('offers nothing before the first photos', () => {
    const c = created as unknown as Case
    expect(previousStep(c)).toBeUndefined()
    expect(stepTarget(c, 0)).toBeUndefined()
  })
})
