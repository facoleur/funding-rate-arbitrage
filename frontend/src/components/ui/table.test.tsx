import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { DataTable, HeadRow, THead, Td, Th } from './table'

function renderHead(children: React.ReactNode, divider?: boolean) {
  render(
    <DataTable>
      <THead>
        <HeadRow divider={divider}>{children}</HeadRow>
      </THead>
    </DataTable>,
  )
}

function renderBody(children: React.ReactNode) {
  render(
    <DataTable>
      <tbody>
        <tr>{children}</tr>
      </tbody>
    </DataTable>,
  )
}

describe('habillage commun', () => {
  it('applique le même espacement dense à tous les en-têtes', () => {
    renderHead(<Th>Instrument</Th>)
    expect(screen.getByText('Instrument').className).toContain('pb-2 pr-3')
  })

  it('applique le même espacement dense à toutes les cellules', () => {
    renderBody(<Td>42</Td>)
    expect(screen.getByText('42').className).toContain('py-1 pr-3')
  })

  it('pose la bordure sur la cellule, jamais sur la ligne', () => {
    // En mode `border-separate`, la spec CSS impose d'ignorer les bordures de <tr>.
    renderBody(<Td>42</Td>)
    const cell = screen.getByText('42')
    expect(cell.className).toContain('border-b')
    expect(cell.closest('tr')!.className).not.toContain('border-b')
  })

  it('aligne explicitement, car <th> est centré par défaut par le navigateur', () => {
    renderHead(
      <>
        <Th>Gauche</Th>
        <Th align="right">Droite</Th>
        <Th align="center">Centre</Th>
      </>,
    )
    expect(screen.getByText('Gauche').className).toContain('text-left')
    expect(screen.getByText('Droite').className).toContain('text-right')
    expect(screen.getByText('Centre').className).toContain('text-center')
  })
})

describe('points de customisation', () => {
  it('une rangée d’en-tête intermédiaire peut supprimer son trait', () => {
    renderHead(<Th>Exchange</Th>, false)
    expect(screen.getByText('Exchange').className).not.toContain('border-b')
  })

  it('`pad` resserre une cellule là où className serait ignoré par Tailwind', () => {
    renderBody(<Td pad="tight">bid</Td>)
    const cell = screen.getByText('bid')
    expect(cell.className).toContain('pr-1')
    expect(cell.className).not.toContain('pr-3')
  })

  it('className est ajouté sans écraser la base (couleurs, sticky…)', () => {
    renderBody(<Td className="sticky left-0 bg-zinc-950 text-emerald-400">BTC</Td>)
    const cell = screen.getByText('BTC')
    expect(cell.className).toContain('text-emerald-400')
    expect(cell.className).toContain('sticky')
    expect(cell.className).toContain('py-1')
  })

  it('les attributs natifs passent (colSpan, title)', () => {
    renderHead(
      <Th colSpan={2} title="deux colonnes">
        derive
      </Th>,
    )
    const cell = screen.getByText('derive')
    expect(cell.getAttribute('colspan')).toBe('2')
    expect(cell.getAttribute('title')).toBe('deux colonnes')
  })
})
